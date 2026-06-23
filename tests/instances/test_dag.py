"""Tests for instance DAG helpers — pure graph functions, no DB."""

from hopper.instances.dag import (
    build_adjacency,
    get_subtree_nodes,
    topo_order_leaves_first,
    would_create_cycle,
)


class TestWouldCreateCycle:
    def _children_from_edges(self, edges):
        children_of, _ = build_adjacency(edges)
        return lambda node: children_of.get(node, set())

    def test_self_loop(self):
        assert would_create_cycle(lambda _: [], "A", "A") is True

    def test_direct_cycle(self):
        # A -> B exists, adding B -> A would cycle
        get = self._children_from_edges([("A", "B")])
        assert would_create_cycle(get, "B", "A") is True

    def test_indirect_cycle(self):
        # A -> B -> C exists, adding C -> A would cycle
        get = self._children_from_edges([("A", "B"), ("B", "C")])
        assert would_create_cycle(get, "C", "A") is True

    def test_valid_edge(self):
        get = self._children_from_edges([("A", "B")])
        assert would_create_cycle(get, "A", "C") is False

    def test_diamond_no_cycle(self):
        # A -> B, A -> C, B -> D, C -> D — adding A -> D is redundant but legal
        get = self._children_from_edges([("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")])
        assert would_create_cycle(get, "A", "D") is False

    def test_empty_graph(self):
        assert would_create_cycle(lambda _: [], "A", "B") is False


class TestTopoOrderLeavesFirst:
    def test_linear_chain(self):
        # A -> B -> C; expect C, B, A
        order = topo_order_leaves_first(["A", "B", "C"], [("A", "B"), ("B", "C")])
        assert order.index("C") < order.index("B") < order.index("A")

    def test_diamond(self):
        # A -> B, A -> C, B -> D, C -> D
        edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]
        order = topo_order_leaves_first(["A", "B", "C", "D"], edges)
        assert order.index("D") < order.index("B")
        assert order.index("D") < order.index("C")
        assert order.index("B") < order.index("A")
        assert order.index("C") < order.index("A")

    def test_multi_root(self):
        # X -> C, Y -> C (two overseers, one child)
        edges = [("X", "C"), ("Y", "C")]
        order = topo_order_leaves_first(["X", "Y", "C"], edges)
        assert order.index("C") < order.index("X")
        assert order.index("C") < order.index("Y")

    def test_disconnected_nodes(self):
        # Isolated nodes are leaves
        order = topo_order_leaves_first(["A", "B", "C"], [])
        assert set(order) == {"A", "B", "C"}

    def test_single_node(self):
        assert topo_order_leaves_first(["A"], []) == ["A"]

    def test_nodes_from_edges_auto_added(self):
        order = topo_order_leaves_first([], [("A", "B")])
        assert set(order) == {"A", "B"}
        assert order.index("B") < order.index("A")


class TestBuildAdjacency:
    def test_basic(self):
        children_of, parents_of = build_adjacency([("A", "B"), ("A", "C")])
        assert children_of["A"] == {"B", "C"}
        assert parents_of["B"] == {"A"}
        assert parents_of["C"] == {"A"}

    def test_dag(self):
        children_of, parents_of = build_adjacency([("X", "C"), ("Y", "C")])
        assert parents_of["C"] == {"X", "Y"}


class TestGetSubtreeNodes:
    def test_full_tree(self):
        children_of, _ = build_adjacency([("A", "B"), ("A", "C"), ("B", "D")])
        assert get_subtree_nodes("A", children_of) == {"A", "B", "C", "D"}

    def test_leaf(self):
        children_of, _ = build_adjacency([("A", "B")])
        assert get_subtree_nodes("B", children_of) == {"B"}

    def test_diamond(self):
        children_of, _ = build_adjacency([("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")])
        assert get_subtree_nodes("A", children_of) == {"A", "B", "C", "D"}
