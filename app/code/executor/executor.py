import json
import logging
import os
from typing import Dict

from nvflare.apis.executor import Executor
from nvflare.apis.fl_constant import FLContextKey
from nvflare.apis.fl_context import FLContext
from nvflare.apis.shareable import Shareable
from nvflare.apis.signal import Signal
from utils.logger import NFCLogger
from utils.task_constants import LocalComputationPhases
from utils.utils import get_data_directory_path, get_output_directory_path

from . import client_cache_store as ccs
from . import client_executor_methods as cem


class LMEExecutor(Executor):
    def __init__(self):
        logging.info("LMEExecutor initialized")
        self.logger = None

    def execute(
            self,
            task_name: str,
            shareable: Shareable,
            fl_ctx: FLContext,
            abort_signal: Signal,
    ) -> Shareable:
        cache_store = ccs.CacheSerialStore(get_output_directory_path(fl_ctx))

        self.logger = NFCLogger(fl_ctx.get_prop(FLContextKey.CLIENT_NAME) + '.log', get_output_directory_path(fl_ctx),
                                fl_ctx.get_peer_context().get_prop("COMPUTATION_PARAMETERS").get('log_level', "info"))

        outgoing_shareable = Shareable()

        if task_name == LocalComputationPhases.LOCAL_STEP1.value:
            client_result = self._client_step1_local_stats(shareable, fl_ctx, abort_signal,
                                                            cache_store.get_cache_dict())
            cache_store.update_cache_dict(client_result['cache'])
            outgoing_shareable['result'] = client_result['output']
            outgoing_shareable['computation_phase'] = client_result['computation_phase']

        elif task_name == LocalComputationPhases.LOCAL_STEP2.value:
            client_result = self._client_step2_compute_global_products(shareable, fl_ctx, abort_signal,
                                                                       cache_store.get_cache_dict())
            cache_store.update_cache_dict(client_result['cache'])
            outgoing_shareable['result'] = client_result['output']
            outgoing_shareable['computation_phase'] = client_result['computation_phase']

        elif task_name == LocalComputationPhases.LOCAL_STEP3.value:
            client_result = self._client_step3_compute_level_residuals(shareable, fl_ctx, abort_signal,
                                                                        cache_store.get_cache_dict())
            cache_store.update_cache_dict(client_result['cache'])
            outgoing_shareable['result'] = client_result['output']
            outgoing_shareable['computation_phase'] = client_result['computation_phase']

        elif task_name == LocalComputationPhases.LOCAL_STEP4.value:
            client_result = self._client_step4_persist_results(shareable, fl_ctx, abort_signal,
                                                                cache_store.get_cache_dict())
            cache_store.remove_cache()
            self.logger.format_log()

        else:
            raise ValueError(f"Unknown task name: {task_name}")

        self.logger.close()
        return outgoing_shareable

    def _client_step1_local_stats(
            self,
            shareable: Shareable,
            fl_ctx: FLContext,
            abort_signal: Signal,
            cache_dict: Dict
    ) -> Dict:
        data_directory = get_data_directory_path(fl_ctx)
        covariates_path = os.path.join(data_directory, "covariates.csv")
        data_path = os.path.join(data_directory, "data.csv")
        computation_parameters = fl_ctx.get_peer_context().get_prop("COMPUTATION_PARAMETERS")

        return cem.perform_client_step1_local_stats(covariates_path, data_path, computation_parameters,
                                                     self.logger, cache_dict)

    def _client_step2_compute_global_products(
            self,
            shareable: Shareable,
            fl_ctx: FLContext,
            abort_signal: Signal,
            cache_dict: Dict
    ) -> Dict:
        agg_result = shareable.get("result")
        agg_result['curr_site_id'] = fl_ctx.get_prop(key=FLContextKey.CLIENT_NAME, default=None)

        return cem.perform_local_step2_compute_global_products(agg_result, self.logger, cache_dict)

    def _client_step3_compute_level_residuals(
            self,
            shareable: Shareable,
            fl_ctx: FLContext,
            abort_signal: Signal,
            cache_dict: Dict
    ) -> Dict:
        agg_result = shareable.get("result")

        return cem.perform_local_step3_compute_level_residuals(agg_result, self.logger, cache_dict)

    def _client_step4_persist_results(
            self,
            shareable: Shareable,
            fl_ctx: FLContext,
            abort_signal: Signal,
            cache_dict: Dict
    ) -> Dict:
        agg_result = shareable.get("result")
        if agg_result is None:
            raise RuntimeError("Empty aggregation result")

        result = cem.perform_local_step4_persist_results(agg_result, self.logger, cache_dict)
        for output_file_type, output_file_data in result.get('output').items():
            if output_file_type == 'json':
                self._save_json(output_file_data, "global_regression_result.json", fl_ctx)
            if output_file_type == 'html':
                self._save_html(output_file_data, "index.html", fl_ctx)
            if output_file_type == 'csv':
                self._save_stats_csv(output_file_data, fl_ctx)

        return result

    def _save_json(self, data: dict, filename: str, fl_ctx: FLContext) -> None:
        output_dir = get_output_directory_path(fl_ctx)
        output_path = os.path.join(output_dir, filename)
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=4)

    def _save_html(self, data: str, filename: str, fl_ctx: FLContext) -> None:
        output_dir = get_output_directory_path(fl_ctx)
        output_path = os.path.join(output_dir, filename)
        with open(output_path, 'w') as f:
            f.write(data)

    def _save_stats_csv(self, data: dict, fl_ctx: FLContext) -> None:
        output_dir = get_output_directory_path(fl_ctx)
        for name, df in data.items():
            output_path = os.path.join(output_dir, f"{name}.csv")
            df.to_csv(output_path, index_label='ROI')
