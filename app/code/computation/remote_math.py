"""Aggregator-side math for the decentralized LME protocol.

Every function receives its site results keyed by site display name (the
framework resolves provisioned site ids through ``site_id_name_map``), so the
per-site output below is already keyed by the names shown to users.
"""

from typing import Dict

import numpy as np
from framework import with_state

from . import constants
from .labels import OutputDictKeyLabels
from .lme_core import matrix_ops, regression
from .types import (
    GlobalFit,
    GlobalLevels,
    SiteLevelResiduals,
    SiteLevels,
    SiteProducts,
)

PROD_MATRIX_NAMES = ["XtX", "XtY", "XtZ", "YtX", "YtY", "YtZ", "ZtX", "ZtY", "ZtZ"]


def gather_site_levels(site_results: Dict[str, SiteLevels]):
    """Assign each site a column offset into the global Z matrix.

    Aggregates each site's local random-effect level count and observation
    count. Sites are ordered by name so the layout is independent of arrival
    order; each site finds its own offset through the random token it minted
    (see local_math.compute_local_stats).
    """
    sorted_sites = sorted(site_results.keys())

    col_offset_per_token = {}
    running_total = 0
    for site in sorted_sites:
        col_offset_per_token[site_results[site].site_token] = running_total
        running_total += site_results[site].nlevels

    nlevels_global = running_total
    nobservns_global = sum(site_results[site].nobservns for site in sorted_sites)

    state = {
        "nlevels_global": nlevels_global,
        "nobservns_global": nobservns_global,
        "random_factor_labels_per_site": {
            site: site_results[site].random_factor_labels for site in sorted_sites
        },
    }

    return with_state(
        GlobalLevels(
            col_offset_per_token=col_offset_per_token,
            nlevels_global=nlevels_global,
        ),
        state,
    )


def compute_global_model(site_results: Dict[str, SiteProducts], state, parameters):
    """Fit the global PSFS model from the summed site product matrices.

    Sums the local product matrices across all sites, fits the global PSFS
    model once, and assembles the per-ROI 'regressions' output (global_stats +
    local_stats per site), matching the shape of the original compspec output.
    """
    sorted_sites = sorted(site_results.keys())

    XtX, XtY, XtZ, YtX, YtY, YtZ, ZtX, ZtY, ZtZ = [
        sum(getattr(site_results[site], name) for site in sorted_sites)
        for name in PROD_MATRIX_NAMES
    ]

    nlevels_global = np.array([state["nlevels_global"]])
    nobservns_global = state["nobservns_global"]
    nraneffs = np.array([1])

    nfixeffs = XtX.shape[1]
    ndepvars = XtY.shape[0]

    paramVec = regression.pSFS3D(
        XtX,
        XtY,
        XtZ,
        YtX,
        YtY,
        YtZ,
        ZtX,
        ZtY,
        ZtZ,
        nlevels_global,
        nraneffs,
        parameters.get("Tol", constants.PSFS_TOL),
        nobservns_global,
    )

    beta, sigma2, vechD, D = matrix_ops.get_parameter_estimates(
        paramVec, nfixeffs, ndepvars, nlevels_global, nraneffs
    )

    contrasts = parameters["Contrasts"]
    prod_matrices = [XtX, XtY, XtZ, YtX, YtY, YtZ, ZtX, ZtY, ZtZ]
    llh, resms, covB, tstats, fstats = regression.cal_inference(
        prod_matrices,
        nobservns_global,
        nfixeffs,
        ndepvars,
        nlevels_global,
        nraneffs,
        beta,
        sigma2,
        D,
        contrasts,
    )

    global_dict_list = matrix_ops.gen_comp_output_dict(
        beta, sigma2, vechD, llh, resms, covB, tstats, fstats, ndepvars
    )

    y_labels = site_results[sorted_sites[0]].y_labels

    local_lists = [site_results[site].local_param_dict_list for site in sorted_sites]
    transposed = list(map(list, zip(*local_lists, strict=False)))
    local_dict = [
        {
            site: site_stats
            for site, site_stats in zip(sorted_sites, roi_stats, strict=False)
        }
        for roi_stats in transposed
    ]

    dict_list = matrix_ops.get_stats_to_dict(
        [
            OutputDictKeyLabels.ROI.value,
            OutputDictKeyLabels.GLOBAL_STATS.value,
            OutputDictKeyLabels.LOCAL_STATS.value,
        ],
        y_labels,
        global_dict_list,
        local_dict,
    )

    random_factor_labels_per_site = state["random_factor_labels_per_site"]
    random_effect_levels = {
        "total": int(nlevels_global[0]),
        "per_site": {
            site: (random_factor_labels_per_site.get(site) or [])
            for site in sorted_sites
        },
    }

    # Carried forward so merge_level_residuals can attach them to the final
    # output once it has merged each site's per-level residuals in.
    state = {
        "regressions": dict_list,
        "random_effect_levels": random_effect_levels,
    }

    return with_state(
        GlobalFit(beta_global=beta.reshape(ndepvars, nfixeffs)),
        state,
    )


def merge_level_residuals(site_results: Dict[str, SiteLevelResiduals], state):
    """Merge each site's per-level residuals into the final result.

    Combines each site's own per-RandomFactor-level mean residuals (computed
    against the global fit) into one view, nested by site so identically-named
    levels at different sites (e.g. two sites both using the label '1') can't
    collide, and attaches the 'regressions'/'random_effect_levels' output
    finalized by compute_global_model.
    """
    sorted_sites = sorted(site_results.keys())

    level_residuals_per_site = {
        site: site_results[site].level_residuals for site in sorted_sites
    }

    return {
        "regressions": state["regressions"],
        "random_effect_levels": state["random_effect_levels"],
        "level_residuals": {"per_site": level_residuals_per_site},
    }
