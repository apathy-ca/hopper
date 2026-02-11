"""
Task similarity calculations using TF-IDF and tag matching.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SimilarityResult:
    """Result of a similarity calculation."""

    task_id: str
    score: float
    text_score: float = 0.0
    tag_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "score": self.score,
            "text_score": self.text_score,
            "tag_score": self.tag_score,
            "metadata": self.metadata,
        }


class TaskSimilarity:
    """
    Calculate similarity between tasks using TF-IDF and tag matching.

    Uses a simple TF-IDF implementation without external dependencies.
    """

    # Common stop words to filter out
    STOP_WORDS = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
        "be", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "must", "shall", "can", "need",
        "this", "that", "these", "those", "it", "its", "i", "me", "my",
        "we", "us", "our", "you", "your", "he", "him", "his", "she", "her",
        "they", "them", "their", "what", "which", "who", "whom", "when",
        "where", "why", "how", "all", "each", "every", "both", "few", "more",
        "most", "other", "some", "such", "no", "nor", "not", "only", "own",
        "same", "so", "than", "too", "very", "just", "also", "now", "here",
        "there", "then", "once", "if", "else", "any", "into", "out", "up",
        "down", "over", "under", "again", "further", "about", "through",
    }

    def __init__(
        self,
        text_weight: float = 0.6,
        tag_weight: float = 0.4,
        min_token_length: int = 2,
    ):
        """
        Initialize similarity calculator.

        Args:
            text_weight: Weight for text similarity (0-1)
            tag_weight: Weight for tag similarity (0-1)
            min_token_length: Minimum token length to consider
        """
        self.text_weight = text_weight
        self.tag_weight = tag_weight
        self.min_token_length = min_token_length

        # Document frequency cache for IDF
        self._doc_count = 0
        self._doc_freq: Counter[str] = Counter()
        self._corpus_vectors: dict[str, dict[str, float]] = {}
        self._corpus_tags: dict[str, set[str]] = {}

    def tokenize(self, text: str) -> list[str]:
        """
        Tokenize text into words.

        Args:
            text: Text to tokenize

        Returns:
            List of tokens
        """
        if not text:
            return []

        # Lowercase and extract words
        text = text.lower()
        words = re.findall(r"\b[a-z][a-z0-9_-]*\b", text)

        # Filter stop words and short tokens
        tokens = [
            w for w in words
            if w not in self.STOP_WORDS and len(w) >= self.min_token_length
        ]

        return tokens

    def compute_tf(self, tokens: list[str]) -> dict[str, float]:
        """
        Compute term frequency for tokens.

        Uses sublinear TF: 1 + log(count)

        Args:
            tokens: List of tokens

        Returns:
            TF dict
        """
        if not tokens:
            return {}

        counts = Counter(tokens)
        tf = {}
        for term, count in counts.items():
            tf[term] = 1 + math.log(count) if count > 0 else 0
        return tf

    def compute_idf(self, term: str) -> float:
        """
        Compute inverse document frequency for a term.

        Args:
            term: Term to compute IDF for

        Returns:
            IDF score
        """
        if self._doc_count == 0:
            return 0.0

        doc_freq = self._doc_freq.get(term, 0)
        if doc_freq == 0:
            return 0.0

        return math.log(self._doc_count / doc_freq)

    def compute_tfidf(self, tokens: list[str]) -> dict[str, float]:
        """
        Compute TF-IDF vector for tokens.

        Args:
            tokens: List of tokens

        Returns:
            TF-IDF vector
        """
        tf = self.compute_tf(tokens)
        tfidf = {}
        for term, tf_score in tf.items():
            idf = self.compute_idf(term)
            tfidf[term] = tf_score * idf
        return tfidf

    def add_document(
        self,
        task_id: str,
        text: str,
        tags: list[str] | set[str] | dict[str, Any] | None = None,
    ) -> None:
        """
        Add a document to the corpus.

        Args:
            task_id: Task ID
            text: Task text (title + description)
            tags: Task tags
        """
        tokens = self.tokenize(text)

        # Update document frequency
        unique_terms = set(tokens)
        for term in unique_terms:
            self._doc_freq[term] += 1
        self._doc_count += 1

        # Store TF vector (we'll compute TF-IDF at query time)
        tf = self.compute_tf(tokens)
        self._corpus_vectors[task_id] = tf

        # Normalize tags
        if tags is None:
            tag_set = set()
        elif isinstance(tags, dict):
            tag_set = set(tags.keys())
        elif isinstance(tags, (list, set)):
            tag_set = set(tags)
        else:
            tag_set = set()

        self._corpus_tags[task_id] = tag_set

    def remove_document(self, task_id: str) -> bool:
        """
        Remove a document from the corpus.

        Args:
            task_id: Task ID to remove

        Returns:
            True if removed
        """
        if task_id not in self._corpus_vectors:
            return False

        # Update document frequency
        tf = self._corpus_vectors[task_id]
        for term in tf.keys():
            self._doc_freq[term] -= 1
            if self._doc_freq[term] <= 0:
                del self._doc_freq[term]

        self._doc_count -= 1
        del self._corpus_vectors[task_id]
        self._corpus_tags.pop(task_id, None)

        return True

    def cosine_similarity(
        self,
        vec1: dict[str, float],
        vec2: dict[str, float],
    ) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity (0-1)
        """
        if not vec1 or not vec2:
            return 0.0

        # Dot product
        common_terms = set(vec1.keys()) & set(vec2.keys())
        if not common_terms:
            return 0.0

        dot = sum(vec1[t] * vec2[t] for t in common_terms)

        # Magnitudes
        mag1 = math.sqrt(sum(v * v for v in vec1.values()))
        mag2 = math.sqrt(sum(v * v for v in vec2.values()))

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot / (mag1 * mag2)

    def jaccard_similarity(
        self,
        set1: set[str],
        set2: set[str],
    ) -> float:
        """
        Compute Jaccard similarity between two sets.

        Args:
            set1: First set
            set2: Second set

        Returns:
            Jaccard similarity (0-1)
        """
        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        if union == 0:
            return 0.0

        return intersection / union

    def find_similar(
        self,
        text: str,
        tags: list[str] | set[str] | dict[str, Any] | None = None,
        limit: int = 10,
        min_score: float = 0.0,
        exclude_ids: set[str] | None = None,
    ) -> list[SimilarityResult]:
        """
        Find similar tasks in the corpus.

        Args:
            text: Query text
            tags: Query tags
            limit: Maximum results
            min_score: Minimum similarity score
            exclude_ids: Task IDs to exclude

        Returns:
            List of similar tasks
        """
        exclude_ids = exclude_ids or set()

        # Compute query vector
        query_tokens = self.tokenize(text)
        query_tfidf = self.compute_tfidf(query_tokens)

        # Normalize query tags
        if tags is None:
            query_tags = set()
        elif isinstance(tags, dict):
            query_tags = set(tags.keys())
        elif isinstance(tags, (list, set)):
            query_tags = set(tags)
        else:
            query_tags = set()

        results = []

        for task_id, corpus_tf in self._corpus_vectors.items():
            if task_id in exclude_ids:
                continue

            # Compute TF-IDF for corpus document
            corpus_tfidf = {
                term: tf_score * self.compute_idf(term)
                for term, tf_score in corpus_tf.items()
            }

            # Text similarity
            text_score = self.cosine_similarity(query_tfidf, corpus_tfidf)

            # Tag similarity
            corpus_tags = self._corpus_tags.get(task_id, set())
            tag_score = self.jaccard_similarity(query_tags, corpus_tags)

            # Combined score
            score = (
                self.text_weight * text_score
                + self.tag_weight * tag_score
            )

            if score >= min_score:
                results.append(
                    SimilarityResult(
                        task_id=task_id,
                        score=score,
                        text_score=text_score,
                        tag_score=tag_score,
                    )
                )

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)

        return results[:limit]

    def get_corpus_size(self) -> int:
        """Get number of documents in corpus."""
        return self._doc_count

    def clear(self) -> None:
        """Clear the corpus."""
        self._doc_count = 0
        self._doc_freq.clear()
        self._corpus_vectors.clear()
        self._corpus_tags.clear()
