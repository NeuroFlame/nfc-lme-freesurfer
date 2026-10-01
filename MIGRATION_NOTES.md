# Migration to computation-nvflare-boilerplate

This computation was migrated from the old, hand-written NVFlare
`Controller`/`Executor`/`Aggregator` architecture (NVFlare 2.4, Python 3.8) to
the current
[`computation-nvflare-boilerplate`](https://github.com/NeuroFlame/computation-nvflare-boilerplate)
contract (boilerplate 0.1.0, NVFlare 2.8, Python 3.11), where authors write
only `app/code/computation/` and the boilerplate's `framework/`/`runtime/` own
all NVFlare integration. See the boilerplate's
[migration guide](https://github.com/NeuroFlame/computation-nvflare-boilerplate/blob/main/docs/computation_development/migrating_computations.md)
for the general process.

Applied from boilerplate commit `dbc9503`; `scripts/migrate_computation.py
--check` reports 0 differing managed paths.

## How the old code maps to the new layout

The protocol is unchanged: three local/remote exchanges and a final site
output step, declared as one `stepped_workflow` in
`app/code/computation/spec.py`.

| Old task (`executor`/`aggregator`) | New function |
| --- | --- |
| `local_step1` / `remote_step1` | `load_inputs` + `compute_local_stats` / `gather_site_levels` |
| `local_step2` / `remote_step2` | `compute_global_products` / `compute_global_model` |
| `local_step3` / `remote_step3` | `compute_level_residuals` / `merge_level_residuals` |
| `local_step4` | `build_outputs` |

| Old module | New module |
| --- | --- |
| `executor/client_executor_methods.py` | `computation/local_math.py`, `computation/results.py` |
| `executor/client_input_preprocessor.py` | `computation/validation.py`, `computation/inputs.py` |
| `executor/client_constants.py` | `computation/constants.py` |
| `aggregator/aggregator_methods.py` | `computation/remote_math.py` |
| `utils/ancillary.py` | `computation/labels.py` |
| `lme_core/` | `computation/lme_core/` (moved, byte-for-byte unchanged) |
| `controller/`, `executor/executor.py`, `executor/client_cache_store.py`, `aggregator/aggregator.py`, `utils/` | removed; replaced by `framework/` and `runtime/` |

Payloads and cached state are now dataclasses (`computation/types.py`), and
matrices travel as NumPy arrays instead of nested lists.

## Intentional differences

- **A site finds its own Z-matrix offset through a random token, not its
  NVFlare identity.** The old code read `FLContextKey.CLIENT_NAME` to look up
  its column offset in `col_offset_per_site`. The framework does not expose a
  site's own identity to computation code, so each site mints a random
  `site_token` in `compute_local_stats`, and `gather_site_levels` returns the
  offsets keyed by token.
- **Sites are ordered by display name instead of raw site ID.** The framework
  hands remote functions their site results keyed by display name (resolved
  through `site_id_name_map`). This sets the column order of the global Z
  matrix and the order of the per-site entries in the output. When display
  names sort the same way as site IDs (always the case in the simulator) the
  output is byte-identical to the old implementation. When they sort
  differently, per-site entries are listed alphabetically by display name and
  the numbers agree to floating-point rounding (see below).
- **Logs.** Each site now writes a plain-text `<site>.log` through the
  framework's logger; the old JSON-lines log and its `<site>-Formatted.log`
  companion are gone. The aggregator log moved from `None/aggregator.log` to
  `server/aggregator.remote.log`.
- **Dependencies.** Dropped `simplejson` (only used by the removed cache store)
  and `dominate` (unused). `nvflare` 2.4.0 → 2.8.0 and the base image Python
  3.8 → 3.11 per the boilerplate's pins; `numpy`, `pandas`, `scipy`,
  `statsmodels` and `patsy` pins are unchanged. `distutils.util.strtobool`
  (removed in Python 3.12) was replaced by an equivalent local helper.
- `app/code/computation/lme_core/ruff.toml` excludes the vendored PSFS/BLMM
  routines from lint/format so they stay identical to upstream; a nested config
  is used because the root `pyproject.toml` is migration-managed.

## Verification performed

- **Output parity, two sites** (`test_data`: `site1`, `site2`): a baseline was
  captured from the pre-migration implementation (commit `7ea2a37`) in its own
  NVFlare 2.4 image. The migrated implementation's
  `global_regression_result.json`, `index.html`, `global_stats.csv` and
  `local_stats_<site>.csv` are byte-identical at both sites (10 of 10 files).
- **Output parity, four sites** (an external dataset with a string covariate,
  named random-effect levels and `IgnoreSubjectsWithMissingData: true`):
  byte-identical at all four sites (28 of 28 files).
- **Site display names**: both implementations were run on the four-site
  dataset with a `site_id_name_map` whose names sort in the reverse order of
  the site IDs. Same output files and keys; the largest relative difference in
  any number in `global_regression_result.json` is 1.7e-11.
- **`make check`**: lint, format, compile and unit tests all pass.
- **Image validation**: `./dockerPush.sh --no-push` builds the production
  image and validates its OCI/NeuroFLAME labels.

**Not verified**: a run through an actual NeuroFLAME platform stack (central
API plus edge sites). Everything above ran in the NVFlare simulator.
