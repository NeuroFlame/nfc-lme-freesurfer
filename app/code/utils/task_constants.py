from enum import Enum, unique


# Task names
@unique
class LocalComputationPhases(Enum):
    LOCAL_STEP1 = "local_step1"
    LOCAL_STEP2 = "local_step2"
    LOCAL_STEP3 = "local_step3"
    LOCAL_STEP4 = "local_step4"


@unique
class AggregatorComputationPhases(Enum):
    AGG_STEP1 = "remote_step1"
    AGG_STEP2 = "remote_step2"
    AGG_STEP3 = "remote_step3"


# Component IDs
LME_AGGREGATOR_ID = "lme_aggregator"
