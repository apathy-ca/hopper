"""
Delegation protocol package.

Implements the logic for routing tasks down the instance hierarchy
and bubbling completion status back up.
"""

from .completion import CompletionBubbler
from .delegator import Delegator, DelegationError
from .policies import DelegationPolicy, get_policy_for_scope
from .router import InstanceRouter, RoutingError

__all__ = [
    "Delegator",
    "DelegationError",
    "InstanceRouter",
    "RoutingError",
    "CompletionBubbler",
    "DelegationPolicy",
    "get_policy_for_scope",
]
