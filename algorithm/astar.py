"""
astar.py — A* en kısa yol algoritması (saf Python).

Başlangıç düğümünden hedef düğüme en kısa yolu ve toplam mesafeyi bulur.
Sezgisel (heuristic) fonksiyon: düğümler arası Öklid (düz çizgi) mesafesi.
Kenar ağırlıkları da Öklid mesafesi olduğundan sezgisel kabul edilebilir
(admissible) ve A* optimal sonucu garanti eder.
"""

import heapq


def _reconstruct_path(came_from, current):
    """came_from zincirini takip ederek başlangıçtan hedefe yolu kur."""
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def a_star(graph, start, goal):
    """
    graph: Graph (neighbors, distance metotları olan)
    start, goal: düğüm kimlikleri
    Döner: (path, cost). Yol yoksa (None, inf).
    """
    open_heap = [(0.0, start)]          # (f_skoru, düğüm) öncelikli kuyruğu
    came_from = {}                      # düğüm -> nereden geldik
    g_score = {start: 0.0}              # başlangıçtan düğüme bilinen en iyi maliyet
    closed = set()

    while open_heap:
        _, current = heapq.heappop(open_heap)

        if current == goal:
            return _reconstruct_path(came_from, current), g_score[current]

        if current in closed:
            continue
        closed.add(current)

        for neighbor, weight in graph.neighbors(current):
            tentative_g = g_score[current] + weight
            if tentative_g < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + graph.distance(neighbor, goal)  # + sezgisel
                heapq.heappush(open_heap, (f, neighbor))

    return None, float("inf")
