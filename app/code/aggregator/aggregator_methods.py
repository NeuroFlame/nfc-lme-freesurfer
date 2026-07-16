import numpy as np

from lme_core import matrix_ops, regression
from utils.ancillary import OutputDictKeyLabels
from utils.task_constants import AggregatorComputationPhases


def perform_remote_step1_gather_site_levels(site_results, agg_cache_dict):
    """
    Aggregates each site's local random-effect level count and observation count,
    assigning each site a column offset into the global random-effects design matrix Z
    (sites ordered by their raw site id, so every site can independently compute the same
    offsets without needing to know the identities of the other sites).
    """
    sorted_site_ids = sorted(site_results.keys())

    nlevels_per_site = {sid: site_results[sid]["nlevels"] for sid in sorted_site_ids}

    col_offset_per_site = {}
    running_total = 0
    for sid in sorted_site_ids:
        col_offset_per_site[sid] = running_total
        running_total += nlevels_per_site[sid]

    nlevels_global = running_total
    nobservns_global = sum(site_results[sid]["nobservns"] for sid in sorted_site_ids)

    random_factor_labels_per_site = {
        sid: site_results[sid].get("random_factor_labels") for sid in sorted_site_ids
    }

    output_dict = {
        "col_offset_per_site": col_offset_per_site,
        "nlevels_global": nlevels_global,
    }

    cache_dict = {
        "nlevels_global": nlevels_global,
        "nobservns_global": nobservns_global,
        "random_factor_labels_per_site": random_factor_labels_per_site,
    }

    computation_output = {
        "output": output_dict,
        "cache": cache_dict,
        "computation_phase": AggregatorComputationPhases.AGG_STEP1.value,
    }

    return computation_output


def perform_remote_step2_compute_global_model(site_results, agg_cache_dict):
    """
    Sums the local product matrices across all sites, fits the global PSFS model once,
    and assembles the per-ROI 'regressions' output (global_stats + local_stats per site),
    matching the shape of the original compspec output.
    """
    sorted_site_ids = sorted(site_results.keys())

    prod_matrix_names = ["XtX", "XtY", "XtZ", "YtX", "YtY", "YtZ", "ZtX", "ZtY", "ZtZ"]
    summed_matrices = []
    for name in prod_matrix_names:
        summed = sum(np.array(site_results[sid][name]) for sid in sorted_site_ids)
        summed_matrices.append(summed)

    XtX, XtY, XtZ, YtX, YtY, YtZ, ZtX, ZtY, ZtZ = summed_matrices

    nlevels_global = np.array([agg_cache_dict["nlevels_global"]])
    nobservns_global = agg_cache_dict["nobservns_global"]
    nraneffs = np.array([1])

    nfixeffs = XtX.shape[1]
    ndepvars = XtY.shape[0]

    paramVec = regression.pSFS3D(
        XtX, XtY, XtZ, YtX, YtY, YtZ, ZtX, ZtY, ZtZ, nlevels_global, nraneffs,
        agg_cache_dict.get("tol", 1e-6), nobservns_global)

    beta, sigma2, vechD, D = matrix_ops.get_parameter_estimates(
        paramVec, nfixeffs, ndepvars, nlevels_global, nraneffs)

    contrasts = agg_cache_dict["contrasts"]
    prod_matrices = [XtX, XtY, XtZ, YtX, YtY, YtZ, ZtX, ZtY, ZtZ]
    llh, resms, covB, tstats, fstats = regression.cal_inference(
        prod_matrices, nobservns_global, nfixeffs, ndepvars, nlevels_global, nraneffs,
        beta, sigma2, D, contrasts)

    global_dict_list = matrix_ops.gen_comp_output_dict(
        beta, sigma2, vechD, llh, resms, covB, tstats, fstats, ndepvars)

    y_labels = site_results[sorted_site_ids[0]]["y_labels"]

    site_id_name_map = agg_cache_dict.get("site_id_name_map", {})
    display_names = [site_id_name_map.get(sid, sid) for sid in sorted_site_ids]

    local_lists = [site_results[sid]["local_param_dict_list"] for sid in sorted_site_ids]
    transposed = list(map(list, zip(*local_lists)))
    local_dict = [
        {name: value for name, value in zip(display_names, roi_stats)}
        for roi_stats in transposed
    ]

    dict_list = matrix_ops.get_stats_to_dict(
        [OutputDictKeyLabels.ROI.value, OutputDictKeyLabels.GLOBAL_STATS.value, OutputDictKeyLabels.LOCAL_STATS.value],
        y_labels, global_dict_list, local_dict)

    random_factor_labels_per_site = agg_cache_dict.get("random_factor_labels_per_site", {})
    random_effect_levels = {
        "total": int(nlevels_global[0]),
        "per_site": {
            site_id_name_map.get(sid, sid): (random_factor_labels_per_site.get(sid) or [])
            for sid in sorted_site_ids
        },
    }

    output_dict = {"regressions": dict_list, "random_effect_levels": random_effect_levels}

    computation_output = {
        "output": output_dict,
        "cache": {},
        "computation_phase": AggregatorComputationPhases.AGG_STEP2.value,
    }

    return computation_output
