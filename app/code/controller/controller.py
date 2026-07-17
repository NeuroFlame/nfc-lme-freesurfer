import json
from typing import Callable

from nvflare.apis.fl_context import FLContext
from nvflare.apis.impl.controller import Controller, Task, ClientTask
from nvflare.apis.shareable import Shareable
from nvflare.apis.signal import Signal
from utils.task_constants import LME_AGGREGATOR_ID, LocalComputationPhases
from utils.utils import get_parameters_file_path


class LMEController(Controller):
    """
    LMEController drives the 4-round decentralized LME protocol:
    1. LOCAL_STEP1: sites report local random-effect level/observation counts.
    2. LOCAL_STEP2: sites compute product matrices against the global random-effects
       structure and send them to the aggregator, which fits the global model.
    3. LOCAL_STEP3: sites compute their own per-RandomFactor-level mean residuals
       against the global fit; the aggregator merges these across all sites.
    4. LOCAL_STEP4: sites persist the final global regression result.
    """

    ### Framework-Specific Setup: No modification needed ###
    def __init__(
            self,
            min_clients: int = 1,
            wait_time_after_min_received: int = 10,
            task_timeout: int = 0,
    ):
        super().__init__()
        self._task_timeout = task_timeout
        self._min_clients = min_clients
        self._wait_time_after_min_received = wait_time_after_min_received

    #### Computation Author Defined Section ####

    def start_controller(self, fl_ctx: FLContext) -> None:
        self.lme_aggregator = self._engine.get_component(LME_AGGREGATOR_ID)
        self._load_and_set_computation_parameters(fl_ctx)

    def control_flow(self, abort_signal: Signal, fl_ctx: FLContext) -> None:
        # --------STEP 1
        fl_ctx.set_prop(key="CURRENT_ROUND", value=LocalComputationPhases.LOCAL_STEP1.value)
        self._broadcast_task(
            task_name=LocalComputationPhases.LOCAL_STEP1.value,
            data=Shareable(),
            result_cb=self._accept_site_result,
            fl_ctx=fl_ctx,
            abort_signal=abort_signal,
        )
        aggregate_result = self.lme_aggregator.aggregate(fl_ctx)

        # --------STEP 2
        fl_ctx.set_prop(key="CURRENT_ROUND", value=LocalComputationPhases.LOCAL_STEP2.value)
        self._broadcast_task(
            task_name=LocalComputationPhases.LOCAL_STEP2.value,
            data=aggregate_result,
            result_cb=self._accept_site_result,
            fl_ctx=fl_ctx,
            abort_signal=abort_signal,
        )
        aggregate_result = self.lme_aggregator.aggregate(fl_ctx)

        # --------STEP 3
        fl_ctx.set_prop(key="CURRENT_ROUND", value=LocalComputationPhases.LOCAL_STEP3.value)
        self._broadcast_task(
            task_name=LocalComputationPhases.LOCAL_STEP3.value,
            data=aggregate_result,
            result_cb=self._accept_site_result,
            fl_ctx=fl_ctx,
            abort_signal=abort_signal,
        )
        aggregate_result = self.lme_aggregator.aggregate(fl_ctx)

        # --------STEP 4 - END (final broadcast, no callback: sites persist their own copy)
        fl_ctx.set_prop(key="CURRENT_ROUND", value=LocalComputationPhases.LOCAL_STEP4.value)
        self._broadcast_task(
            task_name=LocalComputationPhases.LOCAL_STEP4.value,
            data=aggregate_result,
            result_cb=None,
            fl_ctx=fl_ctx,
            abort_signal=abort_signal,
        )

    def _accept_site_result(self, client_task: ClientTask, fl_ctx: FLContext) -> bool:
        return self.lme_aggregator.accept(client_task.result, fl_ctx)

    #### End of Computation Author Defined Section ####

    #### Framework Helper Methods: No modification necessary ####

    def _broadcast_task(self, task_name: str, data: Shareable, result_cb: Callable[[ClientTask, FLContext], bool],
                        fl_ctx: FLContext, abort_signal: Signal) -> None:
        self.broadcast_and_wait(
            task=Task(
                name=task_name,
                data=data,
                props={},
                timeout=self._task_timeout,
                result_received_cb=result_cb,
            ),
            min_responses=self._min_clients,
            wait_time_after_min_received=self._wait_time_after_min_received,
            fl_ctx=fl_ctx,
            abort_signal=abort_signal,
        )

    def _load_and_set_computation_parameters(self, fl_ctx: FLContext) -> None:
        with open(get_parameters_file_path(fl_ctx), 'r') as f:
            fl_ctx.set_prop(
                key="COMPUTATION_PARAMETERS",
                value=json.load(f),
                private=False,
                sticky=True
            )

    #### Framework-Specific Required Methods: No modification necessary ####

    def process_result_of_unknown_task(self, task: Task, fl_ctx: FLContext) -> None:
        pass

    def stop_controller(self, fl_ctx: FLContext) -> None:
        pass
