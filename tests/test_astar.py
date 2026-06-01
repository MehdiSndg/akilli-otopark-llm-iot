"""
test_astar.py — A* algoritması testleri (bilinen küçük graflar).
"""

from algorithm.graph import Graph
from algorithm.astar import a_star


def _small_graph():
    """A-B-C düz hat (kısa) ve A-D-C dolambaç (uzun) içeren küçük graf."""
    g = Graph()
    for node, (x, y) in {"A": (0, 0), "B": (1, 0), "C": (2, 0), "D": (1, 2)}.items():
        g.add_node(node, x, y)
    g.add_edge("A", "B")   # 1.0
    g.add_edge("B", "C")   # 1.0
    g.add_edge("A", "D")   # ~2.24
    g.add_edge("D", "C")   # ~2.24
    return g


def test_finds_shortest_path():
    g = _small_graph()
    path, cost = a_star(g, "A", "C")
    assert path == ["A", "B", "C"]      # dolambaçlı değil, düz hat
    assert round(cost, 5) == 2.0


def test_start_equals_goal():
    g = _small_graph()
    path, cost = a_star(g, "A", "A")
    assert path == ["A"]
    assert cost == 0.0


def test_no_path_returns_inf():
    g = Graph()
    g.add_node("A", 0, 0)
    g.add_node("B", 5, 5)   # kenar yok -> ulaşılamaz
    path, cost = a_star(g, "A", "B")
    assert path is None
    assert cost == float("inf")
