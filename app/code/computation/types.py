"""Define the values exchanged between sites and the aggregator.

The decentralized LME protocol is three local/remote exchanges followed by a
site output step (see spec.py). Each exchange has its own site payload and
aggregated payload below; ``LocalState`` is what a site keeps on disk between
its own steps and never leaves the site.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class SiteInputs:
    """Validated site-local inputs, handed from the loader to the first step."""

    covariates: pd.DataFrame
    dependents: pd.DataFrame
    # Dense 1..n local random-effect level of each row.
    random_factor: pd.Series
    # Sorted distinct raw labels behind those levels, or None when the site has
    # no random-effect column (a single level).
    random_factor_labels: Optional[List[str]]


@dataclass
class LocalState:
    """Site-local design matrices and local fit cached across steps."""

    X: np.ndarray  # (n, nfixeffs), leading intercept column
    Y: np.ndarray  # (n, ndepvars)
    random_factor: np.ndarray  # (n,), 1-indexed local level codes
    random_factor_labels: Optional[List[str]]
    y_labels: List[str]
    local_param_dict_list: List[Dict[str, Any]]
    # Random token identifying this site in aggregated payloads; the framework
    # does not expose a site's own identity to computation code.
    site_token: str


@dataclass
class SiteLevels:
    """Exchange 1, site to aggregator: this site's random-effect structure."""

    site_token: str
    nlevels: int
    nobservns: int
    random_factor_labels: Optional[List[str]]


@dataclass
class GlobalLevels:
    """Exchange 1, aggregator to sites: the global random-effects layout."""

    # Column offset of each site's levels in the global Z matrix, by site_token.
    col_offset_per_token: Dict[str, int]
    nlevels_global: int


@dataclass
class SiteProducts:
    """Exchange 2, site to aggregator: product matrices against the global Z."""

    XtX: np.ndarray
    XtY: np.ndarray
    XtZ: np.ndarray
    YtX: np.ndarray
    YtY: np.ndarray
    YtZ: np.ndarray
    ZtX: np.ndarray
    ZtY: np.ndarray
    ZtZ: np.ndarray
    y_labels: List[str]
    local_param_dict_list: List[Dict[str, Any]]


@dataclass
class GlobalFit:
    """Exchange 2, aggregator to sites: the global fixed-effects estimates."""

    beta_global: np.ndarray  # (ndepvars, nfixeffs)


@dataclass
class SiteLevelResiduals:
    """Exchange 3, site to aggregator: mean residual per level per ROI."""

    level_residuals: Dict[str, Dict[str, float]]
