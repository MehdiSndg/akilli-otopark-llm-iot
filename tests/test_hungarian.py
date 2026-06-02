"""
test_hungarian.py — Hungarian (optimal atama) algoritması testleri.

Bilinen küçük matrislerde optimal toplam maliyeti ve geçerli (birebir) atamayı
doğrular.
"""

from algorithm.hungarian import hungarian


def _total(cost, assign):
    return sum(cost[i][assign[i]] for i in range(len(assign)))


def test_known_3x3_optimum():
    # Optimal: 0->1 (1), 1->0 (2), 2->2 (2) = 5
    cost = [[4, 1, 3],
            [2, 0, 5],
            [3, 2, 2]]
    assign = hungarian(cost)
    assert _total(cost, assign) == 5
    assert sorted(assign) == [0, 1, 2]          # birebir (her sütun bir kez)


def test_identity_diagonal():
    # Köşegen 0, diğerleri büyük -> köşegen atanmalı
    cost = [[0, 9, 9],
            [9, 0, 9],
            [9, 9, 0]]
    assign = hungarian(cost)
    assert assign == [0, 1, 2]
    assert _total(cost, assign) == 0


def test_rectangular_more_columns():
    # 2 araç, 3 yer: her araç farklı bir yere, toplam en küçük
    cost = [[5, 1, 8],
            [2, 9, 3]]
    assign = hungarian(cost)
    assert len(assign) == 2
    assert assign[0] != assign[1]               # aynı yere iki araç olmaz
    # En iyi: 0->1 (1), 1->0 (2) = 3
    assert _total(cost, assign) == 3


def test_avoids_greedy_trap():
    # Greedy 0. aracı en ucuz sütun 0'a (1) koyar, sonra 1. araç 0'ı alamaz,
    # sütun 1'e (100) düşer -> toplam 101. Optimal: 0->1 (2), 1->0 (3) = 5.
    cost = [[1, 2],
            [3, 100]]
    assign = hungarian(cost)
    assert _total(cost, assign) == 5
    assert assign == [1, 0]
