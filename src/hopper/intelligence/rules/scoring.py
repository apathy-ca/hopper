"""
Confidence scoring for rules-based routing.

Provides utilities for:
- Calculating confidence scores from rule matches
- Aggregating scores from multiple rules
- Applying rule weights
- Threshold-based decision making
"""

import math


def calculate_confidence(
    score: float,
    weight: float = 1.0,
    min_confidence: float = 0.0,
    max_confidence: float = 1.0,
) -> float:
    """
    Calculate a confidence score from a raw score and weight.

    Args:
        score: Raw match score (0.0-1.0).
        weight: Rule weight (0.0-1.0).
        min_confidence: Minimum confidence to return.
        max_confidence: Maximum confidence to return.

    Returns:
        Confidence score (0.0-1.0).
    """
    confidence = score * weight
    return max(min_confidence, min(max_confidence, confidence))


def aggregate_scores(
    scores: list[float],
    method: str = "max",
    weights: list[float] | None = None,
) -> float:
    """
    Aggregate multiple scores into a single confidence score.

    Args:
        scores: List of scores to aggregate (0.0-1.0 each).
        method: Aggregation method:
            - "max": Take the maximum score
            - "avg": Average of all scores
            - "weighted_avg": Weighted average (requires weights)
            - "product": Product of scores (conservative)
            - "noisy_or": Probabilistic OR (1 - product of (1-score))
        weights: Optional weights for weighted_avg method.

    Returns:
        Aggregated confidence score (0.0-1.0).

    Raises:
        ValueError: If method is unknown or weights are invalid.
    """
    if not scores:
        return 0.0

    if method == "max":
        return max(scores)

    elif method == "avg":
        return sum(scores) / len(scores)

    elif method == "weighted_avg":
        if not weights or len(weights) != len(scores):
            raise ValueError("weighted_avg requires weights of same length as scores")

        total_weight = sum(weights)
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        return weighted_sum / total_weight

    elif method == "product":
        # Conservative: all scores contribute
        result = 1.0
        for score in scores:
            result *= score
        return result

    elif method == "noisy_or":
        # Probabilistic OR: at least one matches
        # Formula: 1 - product of (1 - score_i)
        result = 1.0
        for score in scores:
            result *= 1.0 - score
        return 1.0 - result

    else:
        raise ValueError(f"Unknown aggregation method: {method}")


def apply_threshold(
    confidence: float,
    threshold: float,
    below_threshold_value: float = 0.0,
) -> float:
    """
    Apply a threshold to a confidence score.

    Scores below threshold are set to below_threshold_value.

    Args:
        confidence: Confidence score to threshold.
        threshold: Threshold value (0.0-1.0).
        below_threshold_value: Value to use if below threshold.

    Returns:
        Thresholded confidence score.
    """
    return confidence if confidence >= threshold else below_threshold_value


def calculate_multi_destination_scores(
    destination_scores: list[tuple[str, float]],
    method: str = "softmax",
    temperature: float = 1.0,
) -> list[tuple[str, float]]:
    """
    Calculate normalized scores across multiple destinations.

    Useful when multiple destinations match and we want to show
    relative confidence for each.

    Args:
        destination_scores: List of (destination, raw_score) tuples.
        method: Normalization method:
            - "softmax": Softmax normalization (emphasizes differences)
            - "normalize": Simple normalization (sum to 1.0)
            - "rank": Rank-based scores (1.0, 0.75, 0.5, ...)
        temperature: Softmax temperature (higher = more uniform).

    Returns:
        List of (destination, normalized_score) tuples, sorted by score descending.
    """
    if not destination_scores:
        return []

    if method == "softmax":
        # Softmax: exp(score/temp) / sum(exp(scores/temp))
        scores = [score for _, score in destination_scores]
        exp_scores = [math.exp(s / temperature) for s in scores]
        total = sum(exp_scores)

        if total == 0:
            # All scores are very negative, use uniform
            normalized = [1.0 / len(scores)] * len(scores)
        else:
            normalized = [exp_s / total for exp_s in exp_scores]

        result = [
            (dest, norm_score) for (dest, _), norm_score in zip(destination_scores, normalized)
        ]

    elif method == "normalize":
        # Simple normalization: score / sum(scores)
        total = sum(score for _, score in destination_scores)

        if total == 0:
            # All scores are zero, use uniform
            normalized_score = 1.0 / len(destination_scores)
            result = [(dest, normalized_score) for dest, _ in destination_scores]
        else:
            result = [(dest, score / total) for dest, score in destination_scores]

    elif method == "rank":
        # Rank-based: 1.0 for first, decreasing by 0.25
        sorted_dests = sorted(destination_scores, key=lambda x: x[1], reverse=True)

        result = []
        for i, (dest, _) in enumerate(sorted_dests):
            rank_score = max(0.0, 1.0 - (i * 0.25))
            result.append((dest, rank_score))

    else:
        raise ValueError(f"Unknown normalization method: {method}")

    # Sort by score descending
    result.sort(key=lambda x: x[1], reverse=True)

    return result


def boost_score(
    score: float,
    boost_factor: float,
    method: str = "multiply",
) -> float:
    """
    Boost a score by a factor.

    Args:
        score: Original score (0.0-1.0).
        boost_factor: Boost factor.
        method: Boost method:
            - "multiply": Multiply score by factor
            - "add": Add factor to score
            - "exponential": score^(1/factor) for factor > 1

    Returns:
        Boosted score, clamped to 0.0-1.0.
    """
    if method == "multiply":
        boosted = score * boost_factor

    elif method == "add":
        boosted = score + boost_factor

    elif method == "exponential":
        if boost_factor <= 0:
            return score
        boosted = math.pow(score, 1.0 / boost_factor)

    else:
        raise ValueError(f"Unknown boost method: {method}")

    return max(0.0, min(1.0, boosted))


def decay_score(
    score: float,
    time_delta_seconds: float,
    half_life_seconds: float = 3600.0,
) -> float:
    """
    Apply time-based decay to a score.

    Useful for reducing confidence in old decisions.

    Args:
        score: Original score (0.0-1.0).
        time_delta_seconds: Time elapsed since decision.
        half_life_seconds: Time for score to decay to half (default 1 hour).

    Returns:
        Decayed score (0.0-1.0).
    """
    if time_delta_seconds <= 0 or half_life_seconds <= 0:
        return score

    decay_factor = math.pow(0.5, time_delta_seconds / half_life_seconds)
    return score * decay_factor


def combine_confidence_and_feedback(
    initial_confidence: float,
    success_rate: float | None,
    feedback_weight: float = 0.3,
) -> float:
    """
    Combine initial confidence with historical feedback.

    Args:
        initial_confidence: Confidence from current evaluation (0.0-1.0).
        success_rate: Historical success rate (0.0-1.0) or None if no history.
        feedback_weight: How much to weight feedback vs initial (0.0-1.0).

    Returns:
        Combined confidence (0.0-1.0).
    """
    if success_rate is None:
        # No feedback yet, use initial confidence
        return initial_confidence

    # Weighted combination
    combined = initial_confidence * (1.0 - feedback_weight) + success_rate * feedback_weight

    return max(0.0, min(1.0, combined))


def estimate_uncertainty(
    scores: list[float],
) -> float:
    """
    Estimate uncertainty in routing decision.

    Higher uncertainty when scores are close together (hard to decide).
    Lower uncertainty when one score is clearly higher (easy decision).

    Args:
        scores: List of confidence scores for different options.

    Returns:
        Uncertainty measure (0.0-1.0), where higher = more uncertain.
    """
    if not scores or len(scores) == 1:
        return 0.0

    sorted_scores = sorted(scores, reverse=True)

    if len(sorted_scores) == 1:
        # Only one option, no uncertainty
        return 0.0

    # Calculate gap between top two scores
    top_score = sorted_scores[0]
    second_score = sorted_scores[1]

    gap = top_score - second_score

    # Small gap = high uncertainty
    # Large gap = low uncertainty
    uncertainty = 1.0 - gap

    return max(0.0, min(1.0, uncertainty))


def should_escalate(
    confidence: float,
    threshold: float,
    uncertainty: float | None = None,
    uncertainty_threshold: float = 0.7,
) -> bool:
    """
    Determine if a routing decision should be escalated to a human.

    Escalate if:
    - Confidence is below threshold
    - Uncertainty is too high (if provided)

    Args:
        confidence: Routing confidence (0.0-1.0).
        threshold: Minimum confidence for automatic routing.
        uncertainty: Optional uncertainty measure (0.0-1.0).
        uncertainty_threshold: Maximum acceptable uncertainty.

    Returns:
        True if should escalate to human, False if can route automatically.
    """
    if confidence < threshold:
        return True

    if uncertainty is not None and uncertainty > uncertainty_threshold:
        return True

    return False


def calculate_rule_quality(
    times_matched: int,
    times_correct: int,
    times_incorrect: int,
    min_samples: int = 5,
) -> float | None:
    """
    Calculate quality score for a rule based on its history.

    Args:
        times_matched: How many times the rule matched.
        times_correct: How many times it was correct.
        times_incorrect: How many times it was incorrect.
        min_samples: Minimum feedback samples before calculating quality.

    Returns:
        Quality score (0.0-1.0) or None if insufficient data.
    """
    total_feedback = times_correct + times_incorrect

    if total_feedback < min_samples:
        return None

    # Success rate
    success_rate = times_correct / total_feedback

    # Apply confidence interval adjustment for small samples
    # Wilson score interval approximation
    if total_feedback < 30:
        # Add Laplace smoothing
        smoothed_success = (times_correct + 1) / (total_feedback + 2)
        return smoothed_success

    return success_rate
