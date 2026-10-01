"""Load and validate one site's inputs for the first computation step."""

import os

from .types import SiteInputs
from .validation import validate_and_get_inputs


def load_inputs(data_dir, parameters, logger) -> SiteInputs:
    """Read and validate this site's covariates.csv/data.csv."""
    covariates_path = os.path.join(data_dir, "covariates.csv")
    data_path = os.path.join(data_dir, "data.csv")

    logger.info(f"Computation parameters received: {parameters}")

    is_valid, X_df, y_df, random_factor, random_factor_labels = validate_and_get_inputs(
        covariates_path, data_path, parameters, logger
    )
    if not is_valid:
        raise ValueError("Invalid run input; see the site log for validation details")

    return SiteInputs(
        covariates=X_df,
        dependents=y_df,
        random_factor=random_factor,
        random_factor_labels=random_factor_labels,
    )
