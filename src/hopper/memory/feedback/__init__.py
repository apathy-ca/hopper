"""
Feedback collection package.

Provides services for collecting and analyzing task feedback
for learning and improving routing decisions.
"""

from .analytics import FeedbackAnalytics
from .store import FeedbackStore

__all__ = [
    "FeedbackStore",
    "FeedbackAnalytics",
]
