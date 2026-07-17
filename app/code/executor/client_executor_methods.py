import copy
import warnings

import numpy as np
import pandas as pd

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import statsmodels.api as sm

from lme_core import matrix_ops, regression
from utils.ancillary import OutputDictKeyLabels
from utils.task_constants import LocalComputationPhases

from . import client_constants
from . import client_input_preprocessor as cip


def perform_client_step1_local_stats(covariates_path, data_path, computation_parameters, logger, cache_dict):
    """
    Reads covariates.csv/data.csv, forms this site's local X/Y/Z design matrices, fits a
    site-local PSFS model (used later purely for 'local_stats' reporting), and reports
    this site's random-effect level count and observation count to the aggregator so a
    global random-effects structure can be formed in step 2.
    """
    logger.info(f"Computation parameters received: {computation_parameters}")

    is_valid, X_df, y_df, random_factor, random_factor_labels = cip.validate_and_get_inputs(
        covariates_path, data_path, computation_parameters, logger)
    if not is_valid:
        raise ValueError(f"Invalid run input. Check validation log at {logger.get_file_name_with_path()}")

    # Encode any residual categorical covariates; no-op for already-numeric/bool columns.
    X_df = pd.get_dummies(X_df, drop_first=True)
    # Fixed-effects design matrix always carries an intercept term (as the leading column),
    # so contrast vectors are indexed [intercept, covariate_1, covariate_2, ...].
    X_df = sm.add_constant(X_df, prepend=True, has_constant='add')

    x_labels = list(X_df.columns)
    y_labels = list(y_df.columns)

    X = X_df.to_numpy(dtype=float)
    Y = y_df.to_numpy(dtype=float)
    random_factor_arr = random_factor.to_numpy(dtype=int)

    Z_local = matrix_ops.form_local_z_matrix(random_factor_arr)

    n = X.shape[0]
    nfixeffs = X.shape[1]
    ndepvars = Y.shape[1]
    nlevels_local = Z_local.shape[1]

    XtX, XtY, XtZ, YtX, YtY, YtZ, ZtX, ZtY, ZtZ = matrix_ops.prod_mats_3d(X, Y, Z_local)

    nlevels_arr = np.array([nlevels_local])
    nraneffs_arr = np.array([1])

    paramVec_local = regression.pSFS3D(
        XtX, XtY, XtZ, YtX, YtY, YtZ, ZtX, ZtY, ZtZ, nlevels_arr, nraneffs_arr,
        client_constants.PSFS_TOL, n)

    beta, sigma2, vechD, D = matrix_ops.get_parameter_estimates(
        paramVec_local, nfixeffs, ndepvars, nlevels_arr, nraneffs_arr)

    contrasts = computation_parameters["Contrasts"]
    prod_matrices = [XtX, XtY, XtZ, YtX, YtY, YtZ, ZtX, ZtY, ZtZ]
    llh, resms, covB, tstats, fstats = regression.cal_inference(
        prod_matrices, n, nfixeffs, ndepvars, nlevels_arr, nraneffs_arr, beta, sigma2, D, contrasts)

    local_param_dict_list = matrix_ops.gen_comp_output_dict(
        beta, sigma2, vechD, llh, resms, covB, tstats, fstats, ndepvars)

    output_dict = {
        "nlevels": nlevels_local,
        "nobservns": n,
        "random_factor_labels": random_factor_labels,
    }

    cache_dict = {
        "x_labels": x_labels,
        "y_labels": y_labels,
        "X": X.tolist(),
        "Y": Y.tolist(),
        "random_factor": random_factor_arr.tolist(),
        "random_factor_labels": random_factor_labels,
        "local_param_dict_list": local_param_dict_list,
        "computation_parameters": computation_parameters,
    }

    computation_output = {
        "output": output_dict,
        "cache": cache_dict,
        "computation_phase": LocalComputationPhases.LOCAL_STEP1.value,
    }

    return computation_output


def perform_local_step2_compute_global_products(agg_result, logger, cache_dict):
    """
    Forms this site's slice of the global random-effects design matrix Z (using the
    column offset assigned by the aggregator) and recomputes the product matrices against
    it, ready for summation across sites.
    """
    col_offset_per_site = agg_result["col_offset_per_site"]
    nlevels_global = agg_result["nlevels_global"]
    curr_site_id = agg_result["curr_site_id"]

    col_offset = col_offset_per_site[curr_site_id]

    X = np.array(cache_dict["X"])
    Y = np.array(cache_dict["Y"])
    random_factor = np.array(cache_dict["random_factor"])

    Z_global = matrix_ops.form_global_z_matrix(nlevels_global, col_offset, random_factor)

    XtX, XtY, XtZ, YtX, YtY, YtZ, ZtX, ZtY, ZtZ = matrix_ops.prod_mats_3d(X, Y, Z_global)

    output_dict = {
        "XtX": XtX.tolist(),
        "XtY": XtY.tolist(),
        "XtZ": XtZ.tolist(),
        "YtX": YtX.tolist(),
        "YtY": YtY.tolist(),
        "YtZ": YtZ.tolist(),
        "ZtX": ZtX.tolist(),
        "ZtY": ZtY.tolist(),
        "ZtZ": ZtZ.tolist(),
        "y_labels": cache_dict["y_labels"],
        "local_param_dict_list": cache_dict["local_param_dict_list"],
    }

    cache_dict = {
        "X": cache_dict["X"],
        "Y": cache_dict["Y"],
        "random_factor": cache_dict["random_factor"],
        "random_factor_labels": cache_dict["random_factor_labels"],
        "y_labels": cache_dict["y_labels"],
        "computation_parameters": cache_dict.get("computation_parameters", {}),
    }

    computation_output = {
        "output": output_dict,
        "cache": cache_dict,
        "computation_phase": LocalComputationPhases.LOCAL_STEP2.value,
    }

    return computation_output


def perform_local_step3_compute_level_residuals(agg_result, logger, cache_dict):
    """
    Computes this site's mean residual (actual - population-average prediction under the
    just-fitted global model) for each of its own RandomFactor levels. This is a simple,
    unshrunk indicator of "what happened at this specific level" (e.g. one institution)
    relative to the federated fixed-effects fit -- not a full BLUP/shrinkage estimate.
    """
    beta_global = np.array(agg_result["beta_global"])  # (ndepvars, nfixeffs)

    X = np.array(cache_dict["X"])  # (n, nfixeffs)
    Y = np.array(cache_dict["Y"])  # (n, ndepvars)
    random_factor = np.array(cache_dict["random_factor"])  # (n,), 1-indexed local codes
    random_factor_labels = cache_dict["random_factor_labels"]
    y_labels = cache_dict["y_labels"]

    Y_hat = X @ beta_global.T
    residuals = Y - Y_hat

    level_residuals = {}
    if random_factor_labels:
        for level, label in enumerate(random_factor_labels, start=1):
            mask = random_factor == level
            mean_residual = residuals[mask].mean(axis=0)
            level_residuals[label] = {y_labels[j]: float(mean_residual[j]) for j in range(len(y_labels))}

    output_dict = {
        "level_residuals": level_residuals,
    }

    cache_dict = {
        "computation_parameters": cache_dict.get("computation_parameters", {}),
    }

    computation_output = {
        "output": output_dict,
        "cache": cache_dict,
        "computation_phase": LocalComputationPhases.LOCAL_STEP3.value,
    }

    return computation_output


def perform_local_step4_persist_results(agg_result, logger, cache_dict):
    """
    Persists the final global regression results in json/csv/html format.
    """
    computation_parameters = cache_dict.get("computation_parameters", {})
    results = {
        "output": {
            "json": copy.deepcopy(agg_result),
            "csv": _get_stats_dataframes(copy.deepcopy(agg_result)),
            "html": _get_html_from_results(copy.deepcopy(agg_result), computation_parameters),
        },
        "cache": {},
        "computation_phase": LocalComputationPhases.LOCAL_STEP4.value,
    }
    return results


def _neglog10_to_p(value):
    """The BLMM/PSFS T2P3D and F2P3D routines return -log10(p), not p itself
    (see regression.py docstrings). Convert back to a plain probability for
    human-readable CSV/HTML output; the JSON output keeps the raw -log10(p)
    value untouched, matching the original compspec."""
    if not isinstance(value, (int, float)):
        return None
    return 10 ** (-value)


def _flatten_stats_entry(stats_entry):
    """Flattens one 'global_stats'/'local_stats[site]' entry (Parameter Estimates +
    Inference Statistics, including per-contrast T/F results) into a flat dict suitable
    for a DataFrame row."""
    flat = {}
    pe = stats_entry.get("Parameter Estimates", {})
    flat["SigmaSquared"] = pe.get("SigmaSquared")
    cov_re = pe.get("CovRandomEffects")
    flat["CovRandomEffects"] = str(cov_re)

    inf = stats_entry.get("Inference Statistics", {})
    flat["Log-likelihood"] = inf.get("Log-likelihood")
    flat["ResidualMeanSquares"] = inf.get("ResidualMeanSquares")

    for tcon in inf.get("T-Contrasts", []):
        name = tcon.get("Contrast Name", "contrast")
        flat[f"{name}_Beta"] = tcon.get("Beta")
        flat[f"{name}_StdErrorBeta"] = tcon.get("StdErrorBeta")
        flat[f"{name}_DOF"] = tcon.get("Degrees of Freedom")
        flat[f"{name}_TStatistic"] = tcon.get("T-Statistic")
        flat[f"{name}_PValue"] = _neglog10_to_p(tcon.get("P-value"))

    for fcon in inf.get("F-Contrasts", []):
        name = fcon.get("Contrast Name", "contrast")
        flat[f"{name}_DOF"] = fcon.get("Degrees of Freedom")
        flat[f"{name}_FStatistic"] = fcon.get("F-Statistic")
        flat[f"{name}_PValue"] = _neglog10_to_p(fcon.get("P-value"))
        flat[f"{name}_RSquared"] = fcon.get("R-Squared")

    return flat


def _get_stats_dataframes(agg_result):
    """Returns {'global_stats': df, 'local_stats_<site>': df, ...} keyed by ROI."""
    regressions = agg_result.get("regressions", [])
    roi_names = [r[OutputDictKeyLabels.ROI.value] for r in regressions]

    result = {}
    global_rows = [_flatten_stats_entry(r[OutputDictKeyLabels.GLOBAL_STATS.value]) for r in regressions]
    result[OutputDictKeyLabels.GLOBAL_STATS.value] = pd.DataFrame(global_rows, index=roi_names)

    site_names = sorted(regressions[0][OutputDictKeyLabels.LOCAL_STATS.value].keys()) if regressions else []
    for site in site_names:
        site_rows = [_flatten_stats_entry(r[OutputDictKeyLabels.LOCAL_STATS.value][site]) for r in regressions]
        result[f"{OutputDictKeyLabels.LOCAL_STATS.value}_{site}"] = pd.DataFrame(site_rows, index=roi_names)

    return result


def _get_html_from_results(agg_result, computation_parameters=None):
    """Returns a self-contained HTML report summarizing the decentralized LME results."""
    import math

    if computation_parameters is None:
        computation_parameters = {}

    regressions = agg_result.get("regressions", [])
    rois = [r[OutputDictKeyLabels.ROI.value] for r in regressions]
    all_sites = sorted(regressions[0][OutputDictKeyLabels.LOCAL_STATS.value].keys()) if regressions else []

    random_effect_levels = agg_result.get("random_effect_levels", {})
    total_levels = random_effect_levels.get("total", len(all_sites))
    levels_per_site = random_effect_levels.get("per_site", {})
    level_residuals_per_site = agg_result.get("level_residuals", {}).get("per_site", {})

    def residual_chip(value):
        if not isinstance(value, (int, float)):
            return ""
        color = "#059669" if value >= 0 else "#dc2626"
        return (f'<span style="font-family:monospace;font-size:.72rem;color:{color};'
                f'font-weight:600">{value:+.3f}</span>')

    _SITE_COLORS_SOLID = [
        "rgba(99,102,241,1.0)", "rgba(20,184,166,1.0)", "rgba(245,158,11,1.0)",
        "rgba(239,68,68,1.0)", "rgba(168,85,247,1.0)", "rgba(34,197,94,1.0)",
    ]
    solid_map = {s: _SITE_COLORS_SOLID[i % len(_SITE_COLORS_SOLID)] for i, s in enumerate(all_sites)}

    def pill(site):
        return (f'<span style="display:inline-flex;align-items:center;gap:.35rem;'
                f'background:{solid_map[site]}22;color:{solid_map[site]};border:1px solid {solid_map[site]};'
                f'border-radius:999px;padding:.18rem .6rem;font-size:.75rem;font-weight:600">'
                f'<span style="width:8px;height:8px;border-radius:50%;background:{solid_map[site]};'
                f'flex-shrink:0"></span>{site}</span>')

    def p_style(p):
        if p is None or not isinstance(p, float) or p >= 0.05:
            return "color:var(--text3)"
        t = math.log(max(p, 1e-10) / 0.05) / math.log(0.001 / 0.05)
        t = max(0.0, min(1.0, t))
        alpha = round(0.08 + t * 0.47, 3)
        weight = "700" if t > 0.55 else "600" if t > 0.2 else "400"
        return f"background:rgba(16,185,129,{alpha});color:#065f46;font-weight:{weight}"

    def p_cell(neglog10_p):
        """Renders a T2P3D/F2P3D result (-log10(p)) as a human-readable p-value cell."""
        p = _neglog10_to_p(neglog10_p)
        if p is None:
            return '<td style="color:var(--text3)">—</td>'
        val = f'{p:.4f}' if p >= 0.0001 else '&lt;0.0001'
        return f'<td style="font-family:monospace;{p_style(p)}">{val}</td>'

    def fnum(v, fmt="%.4f"):
        return fmt % v if isinstance(v, (int, float)) else "—"

    n_covariates = len(computation_parameters.get("Covariates", {}))

    roi_sections = ""
    for result in regressions:
        roi = result[OutputDictKeyLabels.ROI.value]
        gs = result[OutputDictKeyLabels.GLOBAL_STATS.value]
        pe = gs.get("Parameter Estimates", {})
        inf = gs.get("Inference Statistics", {})

        tcon_rows = ""
        for tcon in inf.get("T-Contrasts", []):
            tcon_rows += (f'<tr><td style="font-weight:600">{tcon.get("Contrast Name")}</td>'
                         f'<td style="font-family:monospace">{fnum(tcon.get("Beta"))}</td>'
                         f'<td style="font-family:monospace">{fnum(tcon.get("StdErrorBeta"))}</td>'
                         f'<td style="font-family:monospace">{fnum(tcon.get("Degrees of Freedom"), "%.1f")}</td>'
                         f'<td style="font-family:monospace">{fnum(tcon.get("T-Statistic"), "%.3f")}</td>'
                         f'{p_cell(tcon.get("P-value"))}</tr>')

        fcon_rows = ""
        for fcon in inf.get("F-Contrasts", []):
            fcon_rows += (f'<tr><td style="font-weight:600">{fcon.get("Contrast Name")}</td>'
                         f'<td style="font-family:monospace">{fnum(fcon.get("Degrees of Freedom"), "%.1f")}</td>'
                         f'<td style="font-family:monospace">{fnum(fcon.get("F-Statistic"), "%.3f")}</td>'
                         f'{p_cell(fcon.get("P-value"))}'
                         f'<td style="font-family:monospace">{fnum(fcon.get("R-Squared"))}</td></tr>')

        site_cards = ""
        for site in all_sites:
            ls = result[OutputDictKeyLabels.LOCAL_STATS.value].get(site, {})
            ls_pe = ls.get("Parameter Estimates", {})
            site_labels = levels_per_site.get(site, [])
            site_level_residuals = level_residuals_per_site.get(site, {})

            if site_labels:
                level_rows = "".join(
                    f'<div style="display:flex;justify-content:space-between;padding:.15rem 0 .15rem 1.6rem;font-size:.74rem">'
                    f'<span style="color:var(--text3)">{label} &middot; <span style="font-size:.68rem">&Delta; vs global</span></span>'
                    f'{residual_chip(site_level_residuals.get(label, {}).get(roi))}</div>'
                    for label in site_labels
                )
                labels_note = ""
            else:
                level_rows = ""
                labels_note = '<span style="font-size:.72rem;color:var(--text3)">single level</span>'

            site_cards += (f'<div style="padding:.3rem 0;border-bottom:1px solid var(--border)">'
                          f'<div style="display:flex;justify-content:space-between;align-items:baseline;font-size:.8rem;gap:.6rem">'
                          f'<span style="display:flex;align-items:baseline;gap:.5rem">{pill(site)}{labels_note}</span>'
                          f'<span style="font-family:monospace;color:var(--td-mono);white-space:nowrap" '
                          f'title="Residual variance from an independent model fit using only this site\'s own data">'
                          f'Local &sigma;&sup2; (site-only fit) {fnum(ls_pe.get("SigmaSquared"))}</span></div>'
                          f'{level_rows}</div>')

        roi_sections += f'''<div class="hist-section" style="margin-bottom:1.5rem">
  <div class="hist-header"><div class="hist-title">{roi}</div>
    <span style="font-size:.8rem;color:var(--text3)"><b>Global Log-likelihood:</b> {fnum(inf.get("Log-likelihood"), "%.2f")}
    &middot; <b>Residual MS:</b> {fnum(inf.get("ResidualMeanSquares"), "%.4f")}
    &middot; <b>SigmaSquared:</b> {fnum(pe.get("SigmaSquared"))}
    &middot; <b>Random-Effect Variance:</b> {fnum(pe.get("CovRandomEffects"))}</span>
  </div>
  <div style="padding:1rem 1.4rem">
    {'<div class="stat-card-scroll"><table class="stat-table"><thead><tr><th style="text-align:left">Fixed Effect</th><th>Beta</th><th>Std Err</th><th>DOF</th><th>t</th><th>p-value</th></tr></thead><tbody>' + tcon_rows + '</tbody></table></div>' if tcon_rows else ''}
    {'<div class="stat-card-scroll" style="margin-top:1rem"><table class="stat-table"><thead><tr><th style="text-align:left">Omnibus Test</th><th>DOF</th><th>F</th><th>p-value</th><th>R&sup2;</th></tr></thead><tbody>' + fcon_rows + '</tbody></table></div>' if fcon_rows else ''}
    <div style="margin-top:1rem;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--text3);margin-bottom:.35rem">Per-site local fit</div>
    <div style="font-size:.72rem;color:var(--text3);margin-bottom:.4rem">Level rows show each level's mean (actual − population-average prediction) for {roi}, i.e. how far that level runs above/below what the global fixed-effects fit predicts.</div>
    {site_cards}
  </div>
</div>'''

    roi_pills = "".join(
        f'<span style="background:var(--chip-bg);border:1px solid var(--border);border-radius:999px;'
        f'padding:.2rem .65rem;font-size:.76rem;color:var(--chip-color)">{r}</span>' for r in rois)

    legend = "".join(
        f'<div style="display:flex;align-items:center;gap:.45rem;font-size:.83rem;color:var(--legend-color)">'
        f'<div style="width:11px;height:11px;border-radius:3px;background:{solid_map[s]}"></div>{s}</div>'
        for s in all_sites)

    header = f'''<div class="page-header">
  <h1>Decentralized Linear Mixed Effects Regression</h1>
  <p>Federated LME (PSFS) across {len(all_sites)} site{"s" if len(all_sites)!=1 else ""}</p>
  <p style="font-size:.78rem;color:var(--text3);margin-top:.15rem;max-width:60ch">
    PSFS (Pseudo Simplified Fisher Scoring) is the iterative algorithm — from Tom Maullin's
    <a href="https://github.com/TomMaullin/BLMM" style="color:inherit;text-decoration:underline">BLMM</a>
    package — used to fit this mixed model's fixed- and random-effects parameters.
  </p>
  <div class="chips">
    <div class="chip">Sites <b>{len(all_sites)}</b></div>
    <div class="chip">Outcomes (ROIs) <b>{len(rois)}</b></div>
    <div class="chip">Covariates <b>{n_covariates}</b></div>
    <div class="chip">Random-effect levels <b>{total_levels}</b></div>
  </div>
  <div style="margin-top:.9rem;display:flex;flex-wrap:wrap;gap:.4rem">{roi_pills}</div>
  <div class="site-legend" style="margin-top:.75rem">{legend}</div>
</div>'''

    body = header + f'<div class="container">{roi_sections}</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Federated LME Regression Report</title>
<style>
:root {{
  --bg:#ffffff;--bg3:#f1f5f9;--border:#e2e8f0;--text:#0f172a;--text2:#334155;--text3:#64748b;
  --header-bg:linear-gradient(135deg,#e0e9ff 0%,#f8fafc 100%);--header-border:#e2e8f0;
  --chip-bg:#f1f5f9;--chip-color:#475569;--chip-b:#6366f1;--legend-color:#334155;
  --card-bg:#ffffff;--th-bg:#f8fafc;--td-mono:#1e293b;
}}
[data-theme="dark"] {{
  --bg:#0f172a;--bg3:#0f172a;--border:#334155;--text:#e2e8f0;--text2:#cbd5e1;--text3:#64748b;
  --header-bg:linear-gradient(135deg,#1e1b4b 0%,#0f172a 100%);--header-border:#334155;
  --chip-bg:#1e293b;--chip-color:#94a3b8;--chip-b:#a5b4fc;--legend-color:#cbd5e1;
  --card-bg:#1e293b;--th-bg:#161f30;--td-mono:#cbd5e1;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;margin:1rem 0}}
.page-header{{background:var(--header-bg);border-bottom:1px solid var(--header-border);padding:2rem 2.5rem}}
.page-header h1{{font-size:1.7rem;font-weight:700;color:var(--text);letter-spacing:-.02em}}
.page-header p{{color:var(--text3);margin-top:.35rem;font-size:.93rem}}
.chips{{display:flex;gap:.6rem;margin-top:1rem;flex-wrap:wrap}}
.chip{{background:var(--chip-bg);border:1px solid var(--border);border-radius:999px;padding:.25rem .75rem;font-size:.78rem;color:var(--chip-color)}}
.chip b{{color:var(--chip-b)}}
.site-legend{{display:flex;gap:.9rem;flex-wrap:wrap;margin-top:1rem}}
.container{{max-width:1200px;margin:0 auto;padding:2rem 1.5rem}}
.hist-section{{background:var(--card-bg);border:1px solid var(--border);border-radius:14px;overflow:hidden}}
.hist-header{{padding:1.1rem 1.4rem;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:.8rem;flex-wrap:wrap}}
.hist-title{{font-size:1rem;font-weight:700;color:var(--text)}}
.stat-card-scroll{{overflow-x:auto}}
table.stat-table{{width:100%;border-collapse:collapse;font-size:.8rem}}
table.stat-table th{{color:var(--text3);font-weight:600;padding:.45rem .85rem;text-align:right;background:var(--th-bg)}}
table.stat-table th:first-child{{text-align:left}}
table.stat-table td{{padding:.42rem .85rem;border-top:1px solid var(--border);text-align:right}}
table.stat-table td:first-child{{text-align:left}}
.theme-toggle{{position:fixed;top:1.25rem;right:1.25rem;z-index:999;background:var(--card-bg);border:1px solid var(--border);border-radius:999px;padding:.35rem .85rem;font-size:.8rem;font-weight:600;color:var(--text2);cursor:pointer}}
</style>
</head>
<body>
<button class="theme-toggle" onclick="toggleTheme()" id="themeBtn">🌙 Dark mode</button>
{body}
<script>
function getTheme(){{try{{return localStorage.getItem('theme')||'light'}}catch(e){{return'light'}}}}
function applyTheme(t){{document.documentElement.setAttribute('data-theme',t==='dark'?'dark':'');document.getElementById('themeBtn').textContent=t==='dark'?'☀️ Light mode':'🌙 Dark mode';}}
function toggleTheme(){{var n=getTheme()==='dark'?'light':'dark';try{{localStorage.setItem('theme',n)}}catch(e){{}}applyTheme(n);}}
applyTheme(getTheme());
</script>
</body>
</html>"""
