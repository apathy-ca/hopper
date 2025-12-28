"""
Matching utilities for rules-based routing.

Provides keyword matching, tag matching, pattern matching, and fuzzy matching
utilities used by the rules engine.
"""

import re


def match_keywords(
    text: str,
    keywords: list[str],
    case_sensitive: bool = False,
    whole_word: bool = False,
) -> tuple[list[str], float]:
    """
    Match keywords in text.

    Args:
        text: Text to search in.
        keywords: Keywords to search for.
        case_sensitive: Whether matching is case-sensitive.
        whole_word: Whether to match whole words only.

    Returns:
        Tuple of (matched_keywords, score) where score is 0.0-1.0.
    """
    if not keywords:
        return [], 0.0

    search_text = text if case_sensitive else text.lower()
    search_keywords = keywords if case_sensitive else [k.lower() for k in keywords]

    matched = []

    for keyword in search_keywords:
        if whole_word:
            # Match whole word using regex
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, search_text):
                matched.append(keyword)
        else:
            # Substring match
            if keyword in search_text:
                matched.append(keyword)

    # Calculate score as percentage of keywords matched
    score = len(matched) / len(keywords) if keywords else 0.0

    return matched, score


def match_tags(
    task_tags: list[str],
    required_tags: list[str] | None = None,
    optional_tags: list[str] | None = None,
    tag_patterns: list[str] | None = None,
) -> tuple[bool, list[str], float]:
    """
    Match tags with support for required, optional, and patterns.

    Args:
        task_tags: Tags on the task.
        required_tags: Tags that must all be present.
        optional_tags: Tags that boost score if present.
        tag_patterns: Regex patterns for tag matching.

    Returns:
        Tuple of (matched, matched_tags, score) where:
        - matched: Whether requirements are met
        - matched_tags: List of tags that matched
        - score: Match quality (0.0-1.0)
    """
    task_tag_set = set(task_tags)
    matched_tags = []
    score = 0.0

    # Check required tags
    if required_tags:
        required_set = set(required_tags)
        if not required_set.issubset(task_tag_set):
            # Required tags not met
            return False, [], 0.0

        matched_tags.extend(required_tags)
        score += 0.5  # Base score for meeting requirements

    # Check optional tags
    if optional_tags:
        optional_set = set(optional_tags)
        optional_matched = task_tag_set.intersection(optional_set)

        if optional_matched:
            matched_tags.extend(optional_matched)
            score += 0.3 * (len(optional_matched) / len(optional_tags))

    # Check patterns
    if tag_patterns:
        for pattern in tag_patterns:
            try:
                regex = re.compile(pattern)
                pattern_matches = [tag for tag in task_tags if regex.match(tag)]

                if pattern_matches:
                    matched_tags.extend(pattern_matches)
                    score += 0.2 / len(tag_patterns)  # Distribute score across patterns

            except re.error:
                # Invalid regex pattern, skip
                continue

    # Normalize score
    score = min(score, 1.0)

    # If no criteria specified, match everything with low score
    if not required_tags and not optional_tags and not tag_patterns:
        return True, [], 0.3

    return len(matched_tags) > 0 or score > 0, matched_tags, score


def match_priority(
    task_priority: str | None,
    min_priority: str | None = None,
    max_priority: str | None = None,
    exact_priorities: list[str] | None = None,
) -> tuple[bool, float]:
    """
    Match task priority against criteria.

    Args:
        task_priority: The task's priority level.
        min_priority: Minimum priority (inclusive).
        max_priority: Maximum priority (inclusive).
        exact_priorities: Exact priority values to match.

    Returns:
        Tuple of (matched, score) where score is 0.0-1.0.
    """
    if not task_priority:
        return False, 0.0

    # Priority ordering (lower index = higher priority)
    priority_order = ["critical", "high", "medium", "low"]

    # Check exact matches
    if exact_priorities and task_priority in exact_priorities:
        return True, 1.0

    # Check range
    if min_priority or max_priority:
        try:
            task_idx = priority_order.index(task_priority)

            min_ok = True
            max_ok = True

            if min_priority:
                min_idx = priority_order.index(min_priority)
                min_ok = task_idx <= min_idx  # Lower index = higher priority

            if max_priority:
                max_idx = priority_order.index(max_priority)
                max_ok = task_idx >= max_idx

            if min_ok and max_ok:
                # Calculate score based on how close to min_priority
                if min_priority:
                    distance = abs(task_idx - min_idx)
                    score = 1.0 - (distance * 0.2)  # Decrease by 20% per level
                    return True, max(score, 0.5)  # Minimum 0.5 if in range
                return True, 0.8

        except ValueError:
            # Unknown priority value
            return False, 0.0

    return False, 0.0


def fuzzy_match(
    text: str,
    pattern: str,
    threshold: float = 0.7,
) -> tuple[bool, float]:
    """
    Fuzzy string matching using simple similarity.

    Args:
        text: Text to match against.
        pattern: Pattern to match.
        threshold: Minimum similarity threshold (0.0-1.0).

    Returns:
        Tuple of (matched, similarity) where similarity is 0.0-1.0.
    """
    text = text.lower()
    pattern = pattern.lower()

    # Exact match
    if pattern in text:
        return True, 1.0

    # Calculate simple similarity using longest common substring approach
    similarity = _calculate_similarity(text, pattern)

    matched = similarity >= threshold

    return matched, similarity


def match_pattern(
    text: str,
    pattern: str,
    case_sensitive: bool = False,
) -> tuple[bool, list[str]]:
    """
    Match a regex pattern in text.

    Args:
        text: Text to search.
        pattern: Regex pattern.
        case_sensitive: Whether matching is case-sensitive.

    Returns:
        Tuple of (matched, captured_groups).
    """
    flags = 0 if case_sensitive else re.IGNORECASE

    try:
        match = re.search(pattern, text, flags)

        if match:
            return True, list(match.groups())

        return False, []

    except re.error:
        # Invalid regex
        return False, []


def extract_keywords(
    text: str,
    stopwords: set[str] | None = None,
    min_length: int = 3,
    max_keywords: int = 10,
) -> list[str]:
    """
    Extract potential keywords from text.

    Useful for auto-generating rules or analyzing task content.

    Args:
        text: Text to extract keywords from.
        stopwords: Words to ignore.
        min_length: Minimum word length.
        max_keywords: Maximum keywords to return.

    Returns:
        List of keywords, most significant first.
    """
    if stopwords is None:
        stopwords = _get_default_stopwords()

    # Tokenize and clean
    words = re.findall(r"\b\w+\b", text.lower())

    # Filter stopwords and short words
    keywords = [word for word in words if word not in stopwords and len(word) >= min_length]

    # Count frequency
    word_freq = {}
    for word in keywords:
        word_freq[word] = word_freq.get(word, 0) + 1

    # Sort by frequency
    sorted_keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)

    # Return top keywords
    return [word for word, freq in sorted_keywords[:max_keywords]]


def _calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two strings.

    Uses a simple approach based on common characters and length.

    Args:
        text1: First string.
        text2: Second string.

    Returns:
        Similarity score (0.0-1.0).
    """
    if not text1 or not text2:
        return 0.0

    # Count common characters
    set1 = set(text1)
    set2 = set(text2)
    common = set1.intersection(set2)

    # Calculate Jaccard similarity
    similarity = len(common) / len(set1.union(set2))

    # Bonus for substring match
    if text2 in text1 or text1 in text2:
        similarity = max(similarity, 0.8)

    return similarity


def _get_default_stopwords() -> set[str]:
    """
    Get default English stopwords.

    Returns:
        Set of common stopwords.
    """
    return {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "he",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "that",
        "the",
        "to",
        "was",
        "will",
        "with",
        "this",
        "but",
        "they",
        "have",
        "had",
        "what",
        "when",
        "where",
        "who",
        "which",
        "why",
        "how",
    }


def normalize_score(
    score: float,
    min_score: float = 0.0,
    max_score: float = 1.0,
) -> float:
    """
    Normalize a score to the 0.0-1.0 range.

    Args:
        score: Raw score.
        min_score: Minimum possible score.
        max_score: Maximum possible score.

    Returns:
        Normalized score (0.0-1.0).
    """
    if max_score == min_score:
        return 0.0

    normalized = (score - min_score) / (max_score - min_score)
    return max(0.0, min(1.0, normalized))
