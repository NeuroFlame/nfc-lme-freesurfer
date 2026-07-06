"""
Matrix construction and parameter-extraction helpers for the decentralized LME
computation. Adapted from coinstac-LME-Freesurfer's scripts/lme_utils.py.

`form_global_z_matrix` differs from the original `form_globalZMatrix`: instead
of matching a hardcoded `clientId == 'local' + str(index)` string to infer the
column offset into the global Z matrix, it takes an explicit integer
`col_offset` computed by the caller (see aggregator/aggregator_methods.py),
since NVFlare client (site) names are arbitrary strings, not `local0`/`local1`.
"""
import itertools

import numpy as np

from . import npMatrix3d


def prod_mats_3d(X, Y, Z):
    """
    Forms the product matrices (XtX, XtY, XtZ, YtX, YtY, YtZ, ZtX, ZtY, ZtZ)
    from the design matrices X (n x p), Y (v x n, one row per dependent
    variable) and Z (n x q).
    """
    X = np.array(X)
    Y = np.transpose(np.array(Y))
    Y1 = np.zeros([np.shape(Y)[0], np.shape(Y)[1], 1])
    Y1[:, :, 0] = Y
    Y = Y1
    Z = np.array(Z)

    XtX = (X.transpose() @ X).reshape(1, X.shape[1], X.shape[1])
    XtY = X.transpose() @ Y
    XtZ = (X.transpose() @ Z).reshape(1, X.shape[1], Z.shape[1])
    YtX = XtY.transpose(0, 2, 1)
    YtY = Y.transpose(0, 2, 1) @ Y
    YtZ = Y.transpose(0, 2, 1) @ Z
    ZtX = XtZ.transpose(0, 2, 1)
    ZtY = YtZ.transpose(0, 2, 1)
    ZtZ = (Z.transpose() @ Z).reshape(1, Z.shape[1], Z.shape[1])

    return XtX, XtY, XtZ, YtX, YtY, YtZ, ZtX, ZtY, ZtZ


def form_local_z_matrix(random_factor):
    """
    Forms the local (single-site) random effects design matrix Z of shape
    (n, nlevels_local), one random-intercept column per distinct level found
    in `random_factor` (1-indexed levels, as in the original COINSTAC
    computation).
    """
    random_factor = np.array(random_factor)
    n = len(random_factor)
    nlevels_local = int(np.max(random_factor))

    Z = np.zeros([n, nlevels_local], dtype=int)
    for i in range(n):
        Z[i][random_factor[i] - 1] = 1

    return Z


def form_global_z_matrix(nlevels_global, col_offset, random_factor):
    """
    Forms the global random effects design matrix Z (n x nlevels_global) for
    this site's rows, placing this site's local levels at columns
    [col_offset, col_offset + nlevels_local) of the global matrix.
    """
    random_factor = np.array(random_factor)
    n = len(random_factor)

    Z = np.zeros([n, nlevels_global], dtype=int)
    for i in range(n):
        Z[i][col_offset + random_factor[i] - 1] = 1

    return Z


def get_parameter_estimates(paramVec, p, v, nlevels, nraneffs):
    """
    Extracts beta, sigma2 and D (random effects covariance) from the
    parameter vector returned by regression.pSFS3D.
    """
    q = np.sum(np.dot(nraneffs, nlevels))

    beta = paramVec[:, 0:p]
    sigma2 = paramVec[:, p:(p + 1), :]

    IndsDk = np.int32(np.cumsum(nraneffs * (nraneffs + 1) // 2) + p + 1)
    IndsDk = np.insert(IndsDk, 0, p + 1)

    Ddict = dict()
    Ddict[0] = npMatrix3d.vech2mat3D(paramVec[:, IndsDk[0]:IndsDk[1], :])
    D = npMatrix3d.getDfromDict3D(Ddict, nraneffs, nlevels)

    return beta, sigma2, Ddict[0], D


def get_stats_to_dict(keys, *columns):
    import pandas as pd
    df = pd.DataFrame(list(zip(*columns)), columns=keys)
    return df.to_dict(orient='records')


def gen_comp_output_dict(beta, sigma2, vechD, llh, resms, covB, tstats, fstats, ndepvars):
    """
    Assembles the per-ROI parameter-estimate / inference-statistics dict list,
    matching the shape of the original compspec output (`gen_compoutputdict`).
    """
    param_estimates_keys = ['SigmaSquared', 'CovRandomEffects']
    sigma2_output = [list(itertools.chain.from_iterable(sigma2[i])) for i in range(ndepvars)]
    vechD_output = [list(itertools.chain.from_iterable(vechD[i])) for i in range(ndepvars)]
    sigma2_output = [sigma2_output[i][0] for i in range(ndepvars)]
    vechD_output = [vechD_output[i][0] for i in range(ndepvars)]

    dict_list1 = get_stats_to_dict(param_estimates_keys, sigma2_output, vechD_output)

    param_estimates_keys = ['Contrast Name', 'Contrast Vector', 'Beta', 'StdErrorBeta',
                            'Degrees of Freedom', 'T-Statistic', 'P-value']
    tcon_dict_list_fsregs = []
    for r in range(ndepvars):
        tcon_dict_list = []
        for c in range(len(tstats)):
            Lbeta_output = list(itertools.chain.from_iterable(tstats[c][2][0][r]))
            tcon_dict = get_stats_to_dict(
                param_estimates_keys,
                [tstats[c][0]], [tstats[c][1]],
                Lbeta_output, [tstats[c][2][1][r]],
                [tstats[c][2][2][r]], [tstats[c][2][3][r]],
                [tstats[c][2][4][r]])
            tcon_dict_list.append(tcon_dict[0])
        tcon_dict_list_fsregs.append(tcon_dict_list)

    param_estimates_keys = ['Contrast Name', 'Contrast Vector', 'Degrees of Freedom',
                            'F-Statistic', 'P-value', 'R-Squared']
    fcon_dict_list_fsregs = []
    for r in range(ndepvars):
        fcon_dict_list = []
        for c in range(len(fstats)):
            fcon_dict = get_stats_to_dict(
                param_estimates_keys,
                [fstats[c][0]], [fstats[c][1]],
                [fstats[c][2][0][r]], [fstats[c][2][1][r]],
                [fstats[c][2][2][r]], [fstats[c][2][3][r]])
            fcon_dict_list.append(fcon_dict[0])
        fcon_dict_list_fsregs.append(fcon_dict_list)

    param_estimates_keys = ['Log-likelihood', 'ResidualMeanSquares', 'CovBeta',
                            'T-Contrasts', 'F-Contrasts']
    dict_list2 = get_stats_to_dict(param_estimates_keys, llh, resms, covB,
                                    tcon_dict_list_fsregs, fcon_dict_list_fsregs)

    param_estimates_keys = ['Parameter Estimates', 'Inference Statistics']
    dict_list = get_stats_to_dict(param_estimates_keys, dict_list1, dict_list2)

    return dict_list
