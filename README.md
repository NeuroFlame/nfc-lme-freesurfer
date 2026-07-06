### Computation Description

#### Overview

This computation performs a decentralized **Linear Mixed Effects (LME)** regression on
FreeSurfer ROI data across multiple federated sites, with site membership modeled as a
random effect. It is a NeuroFLAME/NVFlare port of
[coinstac-LME-Freesurfer](https://github.com/trendscenter/coinstc-LME-Freesurfer), using
the Pseudo Simplified Fisher Scoring (PSFS) algorithm from Tom Maullin's
[BLMM](https://github.com/TomMaullin/BLMM) (see `BLMM_Notes.pdf` in the original repo for
algorithm details).

Unlike an iterative gradient-descent regression, PSFS/LME here is fit via decentralized
sufficient statistics: each site computes local product matrices from its own data, the
aggregator sums them once, and a single global model fit produces exact (non-approximate)
parameter estimates and inference statistics — equivalent to fitting the model on pooled
data, without any site ever sharing subject-level data.

#### Example

```json
{
    "Dependents": {
        "Left-Lateral-Ventricle": "float",
        "Left-Inf-Lat-Vent": "float"
    },
    "Covariates": {
        "age": "float",
        "isControl": "bool"
    },
    "Contrasts": [
        {"name": {"value": "Intercept"}, "vector": {"value": [1, 0, 0]}},
        {"name": {"value": "age"}, "vector": {"value": [0, 1, 0]}},
        {"name": {"value": "isControl"}, "vector": {"value": [0, 0, 1]}},
        {"name": {"value": "OmnibusF"}, "vector": {"value": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}}
    ],
    "IgnoreSubjectsWithMissingData": false
}
```

#### Settings Specification

The computation requires two CSV files (`covariates.csv`, `data.csv`) per site as input
along with the above example parameter settings.

Below are the specifications for the parameters:

| Variable Name | Type | Description | Allowed Options | Default | Required |
|---|---|---|---|---|---|
| Covariates | dict | Provide all the fixed-effect covariates that need to be considered for regression along with their type, as shown in the example above. | dict | - | ✅ Yes |
| Dependents | dict | Provide all the FreeSurfer ROI columns to regress against, along with their type, as shown in the example above. | dict | - | ✅ Yes |
| Contrasts | list | List of contrasts to test. A 1D `vector` produces a T-contrast; a 2D `vector` (list of rows) produces an F-contrast. Vectors are indexed `[intercept, covariate_1, covariate_2, ...]` — the fixed-effects design matrix always carries a leading intercept column. | list of `{name, vector}` objects | - | ✅ Yes |
| IgnoreSubjectsWithMissingData | boolean | Lets the computation owner decide how to handle subjects with missing or invalid covariate/dependent values. | true or false | false | ❌ No |

#### Data Format Specification

Each site provides two CSV files:

##### Covariates File (`covariates.csv`)

- **Format**: CSV (Comma-Separated Values)
- **Headers**: one column per fixed-effect covariate, matching the `"Covariates"` section
  of `parameters.json`.
- **`RandomFactor` (optional)**: an integer column (1-indexed) grouping rows into random-
  effect levels *within this site's own data* — e.g. a consortium node submitting pooled
  data from several sub-sites can list a different sub-site number per row. If omitted,
  all rows default to level 1 (the whole site is treated as a single random-effect level).
- **Rows**: one row per subject, in the same order as `data.csv`.

**General Structure**:
```csv
<Covariate_1>,<Covariate_2>,...,<Covariate_N>,RandomFactor
<value_1>,<value_2>,...,<value_N>,1
<value_1>,<value_2>,...,<value_N>,1
...
```

##### Dependent Variables File (`data.csv`)

- **Format**: CSV (Comma-Separated Values)
- **Headers**: one column per ROI, matching the `"Dependents"` section of
  `parameters.json`.
- **Rows**: one row per subject, matching `covariates.csv`.

**General Structure**:
```csv
<Dependent_1>,<Dependent_2>,...,<Dependent_N>
<value_1>,<value_2>,...,<value_N>
<value_1>,<value_2>,...,<value_N>
...
```

#### Algorithm Description

The key steps of the algorithm include:

1. **Local random-effects reporting (`local_step1` / `remote_step1`)**: each site reads
   `covariates.csv` + `data.csv`, forms its local fixed-effects design matrix X (with an
   intercept), dependent variable matrix Y (one column per ROI), and random-effects design
   matrix Z (one random-intercept level per distinct value of the optional `RandomFactor`
   column). Each site also fits a site-local PSFS model, kept only for later `local_stats`
   reporting. Sites report their local level/observation counts; the aggregator assigns
   each site a column offset into the global Z matrix.

2. **Global product matrix aggregation (`local_step2` / `remote_step2`)**: each site forms
   its slice of the global Z matrix (using the offset from step 1) and recomputes its
   product matrices (XtX, XtY, XtZ, YtX, YtY, YtZ, ZtX, ZtY, ZtZ) against it. The
   aggregator sums these across all sites and fits the PSFS model **once**, globally,
   computing beta, sigma2, the random-effects covariance D, and (per the contrasts defined
   in `parameters.json`) log-likelihood, residual mean squares, covariance of beta, and
   T-/F-contrast statistics for every ROI.

3. **Persist results (`local_step3`)**: the final per-ROI regression results (global +
   per-site) are broadcast back and each site saves its own copy of
   `global_regression_result.json`, `index.html`, and one CSV per stats group
   (`global_stats.csv`, `local_stats_<site>.csv`).

#### Assumptions

- The `covariates.csv` and `data.csv` provided by each site follow the specified format
  (standardized covariate and dependent variable headers, matching rows/order).
- `Contrasts` are defined once, centrally, in `parameters.json` — all sites use the same
  contrasts (unlike the original COINSTAC computation, which allowed per-site contrast
  input; only the first site's copy was ever used there).
- `RandomFactor` values, if provided, are positive integers (1-indexed) and only need to
  be locally consistent within a site — they do not need to be globally unique across
  sites.
- The computation is run in a federated environment, and each site contributes valid data.

#### Output Description

- **`global_regression_result.json`**: the `regressions` array — one entry per ROI with
  `ROI`, `global_stats` (SigmaSquared, CovRandomEffects, Log-likelihood,
  ResidualMeanSquares, CovBeta, T-Contrasts, F-Contrasts) and `local_stats` (the same
  shape, per site, from each site's local-only fit).
- **`index.html`**: a self-contained, dark/light-mode report summarizing global and
  per-site fits for every ROI.
- **`global_stats.csv`, `local_stats_<site>.csv`**: flattened per-ROI tables for the
  global fit and each site's local fit.

The computation outputs both **site-level** and **global-level** results, which include:
- **SigmaSquared / CovRandomEffects**: fixed-effects residual variance and random-effects
  covariance estimates.
- **T-/F-Contrasts**: beta, standard error, degrees of freedom, T-/F-statistic and p-value
  for every contrast defined in `parameters.json`.
- **T-contrast p-values are one-tailed and sign-aware** (matching FSL's COPE convention,
  inherited from the underlying BLMM/PSFS implementation): a T-contrast tests whether the
  effect is *positive* in the direction of the contrast vector. A large negative
  T-statistic will therefore show a p-value close to 1, not close to 0 — check the sign of
  `Beta`/`T-Statistic` alongside the p-value. F-contrast p-values are the usual (one-sided,
  non-negative-statistic) F-test p-values.
- **Log-likelihood / Residual Mean Squares**: overall model fit diagnostics.

#### Running this computation

To locally run this computation, please clone this repo and run the following:

1. `./dockerRun.sh` (opens a bash terminal inside the docker container; run the following
   commands inside the container terminal)
2. `python makeJob.py site1,site2`
3. `nvflare simulator ./job`

#### Debug this computation using IDE

To debug the code using an IDE, run the `debug.py` script with the following debug
configuration:

1. **Parameters value:** `job -w ./myworkspace -n 2 -c site1,site2` (change the site count
   to match your test data).
2. **Environment Variables value:** `PYTHONUNBUFFERED=1;PYTHONPATH=<your_local_full_path>/nfc-lme-freesurfer/app/code`
