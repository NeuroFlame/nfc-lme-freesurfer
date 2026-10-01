"""String constants used as keys in the computation's output."""

from enum import Enum, unique


@unique
class OutputDictKeyLabels(Enum):
    """Keys of the per-ROI regression output.

    Matches the original compspec 'regressions' output shape.
    """

    ROI = "ROI"
    GLOBAL_STATS = "global_stats"
    LOCAL_STATS = "local_stats"
