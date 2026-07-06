import os
from typing import Dict, Any

from nvflare.apis.fl_constant import ReservedKey
from nvflare.apis.fl_context import FLContext
from nvflare.apis.shareable import Shareable
from nvflare.app_common.abstract.aggregator import Aggregator
from utils.logger import NFCLogger
from utils.task_constants import LocalComputationPhases
from utils.utils import get_output_directory_path

from . import aggregator_methods as am


class LMEAggregator(Aggregator):
    """
    LMEAggregator handles the aggregation of results from multiple client sites across the
    2-round decentralized LME protocol (gather random-effect levels, then sum product
    matrices and fit the global PSFS model).
    """

    def __init__(self):
        super().__init__()
        # Structure: {round_name: {site_id: data}}
        self.site_results: Dict[str, Dict[str, Any]] = {}
        self.logger = None
        self.agg_cache: Dict[str, Any] = {}

    def accept(self, site_result: Shareable, fl_ctx: FLContext) -> bool:
        site_id = site_result.get_peer_prop(key=ReservedKey.IDENTITY_NAME, default=None)
        contribution_round = fl_ctx.get_prop(key="CURRENT_ROUND", default=None)

        if self.logger is None:
            self.logger = NFCLogger('aggregator.log', get_output_directory_path(fl_ctx),
                                    fl_ctx.get_prop(key="log_level", default="info"))

        self.logger.info(f"Aggregator received contribution from {site_id} for round {contribution_round}")
        if contribution_round is None or site_id is None:
            return False

        if contribution_round not in self.site_results:
            self.site_results[contribution_round] = {}

        self.site_results[contribution_round][site_id] = site_result["result"]
        return True

    def aggregate(self, fl_ctx: FLContext) -> Shareable:
        contribution_round = fl_ctx.get_prop(key="CURRENT_ROUND", default=None)
        outgoing_shareable = Shareable()

        if contribution_round == LocalComputationPhases.LOCAL_STEP1.value:
            computation_parameters = fl_ctx.get_prop(key="COMPUTATION_PARAMETERS", default={})
            self.agg_cache["site_id_name_map"] = computation_parameters.get("site_id_name_map", {})
            self.agg_cache["contrasts"] = computation_parameters["Contrasts"]
            self.agg_cache["tol"] = computation_parameters.get("Tol", 1e-6)

            agg_result = am.perform_remote_step1_gather_site_levels(
                self.site_results[contribution_round], self.agg_cache)
            self.agg_cache.update(agg_result.get('cache', {}))
            outgoing_shareable['result'] = agg_result['output']
            outgoing_shareable['computation_phase'] = agg_result['computation_phase']
            return outgoing_shareable

        elif contribution_round == LocalComputationPhases.LOCAL_STEP2.value:
            agg_result = am.perform_remote_step2_compute_global_model(
                self.site_results[contribution_round], self.agg_cache)
            self.agg_cache.update(agg_result.get('cache', {}))
            outgoing_shareable['result'] = agg_result['output']
            outgoing_shareable['computation_phase'] = agg_result['computation_phase']
            self.logger.close()
            self.logger.format_log()
            return outgoing_shareable

        return Shareable()
