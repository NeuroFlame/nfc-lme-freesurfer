from enum import Enum, unique


@unique
class OutputDictKeyLabels(Enum):
    """
    Holds the string constants used for keying the per-ROI regression output,
    matching the original compspec 'regressions' output shape.
    """
    ROI = "ROI"
    GLOBAL_STATS = "global_stats"
    LOCAL_STATS = "local_stats"
