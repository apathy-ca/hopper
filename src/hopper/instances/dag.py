"""Pure graph helpers for the instance DAG.

No database dependency — functions take plain sets/lists and callables,
so they're unit-testable and shared by the ORM repo, CLI, and audit agent.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Iterable


def would_create_cycle(
    get_children: Callable[[str], Iterable[str]],
    parent_id: str,
    child_id: str,
) -> bool:
    """Return True if adding edge (parent_id -> child_id) would create a cycle.

    Walks descendants of child_id; if parent_id is reachable, the new edge
    would close a loop.
    """
    if parent_id == child_id:
        return True
    stack = [child_id]
    seen: set[str] = set()
    while stack:
        node = stack.pop()
        if node == parent_id:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(get_children(node))
    return False


def topo_order_leaves_first(
    nodes: Iterable[str],
    edges: Iterable[tuple[str, str]],
) -> list[str]:
    """Topological sort with leaves (out-degree 0) emitted first.

    Args:
        nodes: All instance IDs to include.
        edges: (parent_id, child_id) pairs.

    Returns:
        Instance IDs ordered so every child precedes all its parents.
        Nodes not connected by any edge appear first (they are leaves).
    """
    all_nodes = set(nodes)
    children_of: dict[str, set[str]] = defaultdict(set)
    parents_of: dict[str, set[str]] = defaultdict(set)

    for parent, child in edges:
        children_of[parent].add(child)
        parents_of[child].add(parent)
        all_nodes.add(parent)
        all_nodes.add(child)

    out_degree = {n: len(children_of[n]) for n in all_nodes}
    queue: deque[str] = deque(n for n in all_nodes if out_degree[n] == 0)

    order: list[str] = []
    seen: set[str] = set()

    while queue:
        n = queue.popleft()
        if n in seen:
            continue
        seen.add(n)
        order.append(n)
        for p in parents_of[n]:
            out_degree[p] -= 1
            if out_degree[p] == 0:
                queue.append(p)

    # Nodes still unseen are in a cycle (shouldn't happen post cycle-detection).
    for n in all_nodes:
        if n not in seen:
            order.append(n)

    return order


def build_adjacency(
    edges: Iterable[tuple[str, str]],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Build parent->children and child->parents maps from edge list."""
    children_of: dict[str, set[str]] = defaultdict(set)
    parents_of: dict[str, set[str]] = defaultdict(set)
    for parent, child in edges:
        children_of[parent].add(child)
        parents_of[child].add(parent)
    return children_of, parents_of


def get_subtree_nodes(
    root: str,
    children_of: dict[str, set[str]],
) -> set[str]:
    """Return all nodes reachable from root following parent->child edges."""
    result: set[str] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node in result:
            continue
        result.add(node)
        stack.extend(children_of.get(node, set()))
    return result
