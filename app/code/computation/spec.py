"""Declare the decentralized LME workflow.

Three local/remote exchanges followed by a site output step:

1. sites report their random-effect level/observation counts; the aggregator
   lays out the global random-effects design matrix Z.
2. sites compute product matrices against the global Z; the aggregator sums
   them and fits the global PSFS model once.
3. sites compute their per-RandomFactor-level mean residuals against the
   global fit; the aggregator merges them into the final result.
4. sites persist the final result (JSON, CSVs, HTML report).
"""

from framework import (
    ComputationSpec,
    local_step,
    remote_step,
    site_output_step,
    stepped_workflow,
)

from .inputs import load_inputs
from .local_math import (
    compute_global_products,
    compute_level_residuals,
    compute_local_stats,
)
from .remote_math import (
    compute_global_model,
    gather_site_levels,
    merge_level_residuals,
)
from .results import build_outputs

SPEC = ComputationSpec(
    workflow=stepped_workflow(
        local_step(fn=compute_local_stats, input_fn=load_inputs),
        remote_step(fn=gather_site_levels),
        local_step(fn=compute_global_products),
        remote_step(fn=compute_global_model),
        local_step(fn=compute_level_residuals),
        remote_step(fn=merge_level_residuals),
        site_output_step(fn=build_outputs),
    ),
)
