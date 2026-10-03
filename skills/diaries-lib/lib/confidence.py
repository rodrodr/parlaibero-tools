from lib.schemas import ConfidenceLevel, ConfidenceScore


def score_to_level(
    value: float,
    threshold_auto: float = 0.85,
    threshold_flag: float = 0.65,
) -> ConfidenceLevel:
    if value >= threshold_auto:
        return ConfidenceLevel.AUTO
    elif value >= threshold_flag:
        return ConfidenceLevel.FLAG
    else:
        return ConfidenceLevel.HALT


def make_confidence(
    value: float,
    explanation: str,
    details: dict = None,
    threshold_auto: float = 0.85,
    threshold_flag: float = 0.65,
) -> ConfidenceScore:
    return ConfidenceScore(
        value=value,
        level=score_to_level(value, threshold_auto, threshold_flag),
        explanation=explanation,
        details=details or {},
    )


def aggregate_confidence(scores: list[float], method: str = "mean") -> float:
    if not scores:
        return 0.0
    if method == "mean":
        return sum(scores) / len(scores)
    elif method == "min":
        return min(scores)
    elif method == "harmonic":
        safe = [s for s in scores if s > 0]
        if not safe:
            return 0.0
        return len(safe) / sum(1 / s for s in safe)
    return sum(scores) / len(scores)
