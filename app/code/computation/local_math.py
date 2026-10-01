"""Site-side math for the decentralized LME protocol."""

import uuid
import warnings

import numpy as np
import pandas as pd
from framework import with_state

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import statsmodels.api as sm

from . import constants
from .lme_core import matrix_ops, regression
from .types import (
    GlobalFit,
    GlobalLevels,
    LocalState,
    SiteInputs,
    SiteLevelResiduals,
    SiteLevels,
    SiteProducts,
)


def compute_local_stats(inputs: SiteInputs, parameters):
    """Form this site's design matrices and report its random-effect structure.

    Forms the local X/Y/Z design matrices, fits a site-local PSFS model (used
    later purely for 'local_stats' reporting), and reports this site's
    random-effect level count and observation count to the aggregator so a
    global random-effects structure can be formed in the next step.

    Also mints a random ``site_token`` kept in local state: the framework does
    not expose this site's own identity to computation code, so the token is
    how this site later recognizes its own column offset among the ones the
    aggregator assigns (see remote_math.gather_site_levels).
    """
    # Encode any residual categorical covariates; no-op for already-numeric/bool columns.
    X_df = pd.get_dummies(inputs.covariates, drop_first=True)
    # Fixed-effects design matrix always carries an intercept term (as the leading column),
    # so contrast vectors are indexed [intercept, covariate_1, covariate_2, ...].
    X_df = sm.add_constant(X_df, prepend=True, has_constant="add")

    y_labels = list(inputs.dependents.columns)

    X = X_df.to_numpy(dtype=float)
    Y = inputs.dependents.to_numpy(dtype=float)
    random_factor_arr = inputs.random_factor.to_numpy(dtype=int)

    Z_local = matrix_ops.form_local_z_matrix(random_factor_arr)

    n = X.shape[0]
    nfixeffs = X.shape[1]
    ndepvars = Y.shape[1]
    nlevels_local = Z_local.shape[1]

    XtX, XtY, XtZ, YtX, YtY, YtZ, ZtX, ZtY, ZtZ = matrix_ops.prod_mats_3d(X, Y, Z_local)

    nlevels_arr = np.array([nlevels_local])
    nraneffs_arr = np.array([1])

    paramVec_local = regression.pSFS3D(
        XtX,
        XtY,
        XtZ,
        YtX,
        YtY,
        YtZ,
        ZtX,
        ZtY,
        ZtZ,
        nlevels_arr,
        nraneffs_arr,
        constants.PSFS_TOL,
        n,
    )

    beta, sigma2, vechD, D = matrix_ops.get_parameter_estimates(
        paramVec_local, nfixeffs, ndepvars, nlevels_arr, nraneffs_arr
    )

    contrasts = parameters["Contrasts"]
    prod_matrices = [XtX, XtY, XtZ, YtX, YtY, YtZ, ZtX, ZtY, ZtZ]
    llh, resms, covB, tstats, fstats = regression.cal_inference(
        prod_matrices,
        n,
        nfixeffs,
        ndepvars,
        nlevels_arr,
        nraneffs_arr,
        beta,
        sigma2,
        D,
        contrasts,
    )

    local_param_dict_list = matrix_ops.gen_comp_output_dict(
        beta, sigma2, vechD, llh, resms, covB, tstats, fstats, ndepvars
    )

    site_token = uuid.uuid4().hex

    site_levels = SiteLevels(
        site_token=site_token,
        nlevels=nlevels_local,
        nobservns=n,
        random_factor_labels=inputs.random_factor_labels,
    )
    state = LocalState(
        X=X,
        Y=Y,
        random_factor=random_factor_arr,
        random_factor_labels=inputs.random_factor_labels,
        y_labels=y_labels,
        local_param_dict_list=local_param_dict_list,
        site_token=site_token,
    )
    return with_state(site_levels, state)


def compute_global_products(global_levels: GlobalLevels, state: LocalState):
    """Recompute this site's product matrices against the global Z matrix.

    Forms this site's slice of the global random-effects design matrix Z (using
    the column offset assigned by the aggregator) and recomputes the product
    matrices against it, ready for summation across sites.
    """
    col_offset = global_levels.col_offset_per_token[state.site_token]

    Z_global = matrix_ops.form_global_z_matrix(
        global_levels.nlevels_global, col_offset, state.random_factor
    )

    XtX, XtY, XtZ, YtX, YtY, YtZ, ZtX, ZtY, ZtZ = matrix_ops.prod_mats_3d(
        state.X, state.Y, Z_global
    )

    return SiteProducts(
        XtX=XtX,
        XtY=XtY,
        XtZ=XtZ,
        YtX=YtX,
        YtY=YtY,
        YtZ=YtZ,
        ZtX=ZtX,
        ZtY=ZtY,
        ZtZ=ZtZ,
        y_labels=state.y_labels,
        local_param_dict_list=state.local_param_dict_list,
    )


def compute_level_residuals(global_fit: GlobalFit, state: LocalState):
    """Compute this site's mean residual for each of its RandomFactor levels.

    The residual is actual - population-average prediction under the
    just-fitted global model. This is a simple, unshrunk indicator of "what
    happened at this specific level" (e.g. one institution) relative to the
    federated fixed-effects fit -- not a full BLUP/shrinkage estimate.
    """
    beta_global = global_fit.beta_global  # (ndepvars, nfixeffs)

    Y_hat = state.X @ beta_global.T
    residuals = state.Y - Y_hat

    level_residuals = {}
    if state.random_factor_labels:
        for level, label in enumerate(state.random_factor_labels, start=1):
            mask = state.random_factor == level
            mean_residual = residuals[mask].mean(axis=0)
            level_residuals[label] = {
                state.y_labels[j]: float(mean_residual[j])
                for j in range(len(state.y_labels))
            }

    return SiteLevelResiduals(level_residuals=level_residuals)
