"""
graph.py — AVM tarzı otopark yerleşimi ve grafı (tek doğruluk kaynağı).

Düzen (gerçek AVM otoparkı gibi, bloklu):
- Park yerleri YATAY bloklara ayrılır; bloklar arasında ve kenarlarda DİKEY yollar
  vardır. Böylece park cepleri asla bir yolun üstüne gelmez.
- N_AISLES adet YATAY araç yolu (aisle) üst üste dizilir; iki yatay yol arasında bir
  "park bandı" bulunur (her bant 2 sıra: üst sıra üstteki yoldan, alt sıra alttaki
  yoldan girilir).
- Dikey yollar yatay yolları birbirine bağlar (blok aralarında). Araç bir yoldan
  diğerine yalnızca bu dikey yollardan geçer -> A* gerçek bir rota seçimi yapar.
- BİRDEN FAZLA giriş (alt köşeler) ve çıkış / AVM kapısı (üst köşeler) vardır.

Düğüm türleri:
- Park yeri:   "A-1" .. "E-48"     (bant harfi + sıra-içi numara; id == node_id)
- Yatay yol:   "AISLE-{a}-{i}"     (a: yol indexi, i: yol üzerindeki durak indexi)
- Giriş:       "ENTRANCE-0", "ENTRANCE-1"
- Çıkış:       "EXIT-0", "EXIT-1"

graph.geom: UI'ın yolları çizmesi için geometri bilgisi (yatay/dikey yol uçları,
kapı bağlantıları, giriş/çıkış listeleri, durak sayısı).
"""

import math
from dataclasses import dataclass

import config

# Giriş/çıkış düğüm adları (sabit; geometriden bağımsız)
ENTRANCES = ["ENTRANCE-0", "ENTRANCE-1"]
EXITS = ["EXIT-0", "EXIT-1"]
ENTRANCE = ENTRANCES[0]   # geriye dönük uyumluluk
EXIT = EXITS[0]

# Koordinat ölçeği: bir bant 4 mantıksal birim yer kaplar
BAND_UNIT = 4


@dataclass
class ParkingSpot:
    id: str
    node_id: str
    type: str          # "normal" | "disabled" | "ev_charging"
    x: float
    y: float
    zone: str          # "giriş yakını" | "çıkış yakını" | "orta"
    occupied: bool = False


class Graph:
    """Ağırlıklı, yönsüz graf. Kenar ağırlıkları düğümler arası Öklid mesafesidir."""

    def __init__(self):
        self._pos = {}
        self._adj = {}
        self.geom = {}     # UI çizimi için geometri (build_parking doldurur)

    def add_node(self, node, x, y):
        self._pos[node] = (float(x), float(y))
        self._adj.setdefault(node, {})

    def add_edge(self, a, b, weight=None):
        if weight is None:
            weight = self.distance(a, b)
        self._adj[a][b] = weight
        self._adj[b][a] = weight

    def neighbors(self, node):
        return self._adj.get(node, {}).items()

    def position(self, node):
        return self._pos[node]

    def distance(self, a, b):
        (x1, y1), (x2, y2) = self._pos[a], self._pos[b]
        return math.hypot(x1 - x2, y1 - y2)

    def nodes(self):
        return list(self._pos.keys())


def _build_stops():
    """
    Yatay yol üzerindeki durakları (x konumları) üret.
    Dönen liste: her eleman {x, kind('spot'|'road'), col}. 'road' durakları dikey
    yolların geçtiği boşluklardır; 'spot' durakları park sütunlarıdır.
    """
    stops = []
    cursor = 0.0
    # Sol kenar dikey yolu
    stops.append({"x": cursor + config.ROAD_GAP / 2, "kind": "road", "col": None})
    cursor += config.ROAD_GAP
    for b in range(config.N_BLOCKS_X):
        for i in range(config.BLOCK_W):
            col = b * config.BLOCK_W + i
            stops.append({"x": cursor + 0.5, "kind": "spot", "col": col})
            cursor += 1.0
        # Blok sonrası dikey yol
        stops.append({"x": cursor + config.ROAD_GAP / 2, "kind": "road", "col": None})
        cursor += config.ROAD_GAP
    return stops, cursor


def _spot_type(band, row, col):
    if band == 0 and row == 0:
        if col < config.NUM_DISABLED_SPOTS:
            return "disabled"
        if col < config.NUM_DISABLED_SPOTS + config.NUM_EV_SPOTS:
            return "ev_charging"
    return "normal"


def _zone(band):
    if band <= 1:
        return "çıkış yakını"
    if band >= config.N_BANDS - 2:
        return "giriş yakını"
    return "orta"


def _spot_id(band, row, col):
    number = row * config.SPOTS_PER_ROW + col + 1
    return f"{chr(ord('A') + band)}-{number}"


def build_parking():
    """Otoparkı kur. (spots, graph) döndürür; graph.geom UI geometrisini içerir."""
    g = Graph()
    spots = []
    n_aisles = config.N_AISLES
    n_bands = config.N_BANDS

    stops, x_max = _build_stops()
    last_i = len(stops) - 1
    road_indices = [i for i, s in enumerate(stops) if s["kind"] == "road"]

    # 1) Yatay yollar: her aisle için tüm duraklarda düğüm + ardışık bağlantı
    for a in range(n_aisles):
        y = a * BAND_UNIT
        for i, s in enumerate(stops):
            g.add_node(f"AISLE-{a}-{i}", s["x"], y)
        for i in range(len(stops) - 1):
            g.add_edge(f"AISLE-{a}-{i}", f"AISLE-{a}-{i + 1}")

    # 2) Dikey yollar: yalnızca 'road' duraklarında yatay yolları bağla
    for i in road_indices:
        for a in range(n_aisles - 1):
            g.add_edge(f"AISLE-{a}-{i}", f"AISLE-{a + 1}-{i}")

    # 3) Park yerleri: her bant = üst sıra + alt sıra; yere giriş ilgili aisle'dan
    for b in range(n_bands):
        for row in range(2):
            y = b * BAND_UNIT + (1 if row == 0 else 3)
            access_aisle = b if row == 0 else b + 1
            for i, s in enumerate(stops):
                if s["kind"] != "spot":
                    continue
                spot_id = _spot_id(b, row, s["col"])
                g.add_node(spot_id, s["x"], y)
                g.add_edge(spot_id, f"AISLE-{access_aisle}-{i}")
                spots.append(ParkingSpot(
                    id=spot_id, node_id=spot_id, type=_spot_type(b, row, s["col"]),
                    x=s["x"], y=float(y), zone=_zone(b),
                ))

    # 4) Çoklu giriş (alt köşeler) ve çıkış / AVM kapısı (üst köşeler)
    bottom = n_aisles - 1
    bottom_y = bottom * BAND_UNIT
    left_x = stops[0]["x"]
    right_x = stops[last_i]["x"]

    g.add_node("ENTRANCE-0", left_x, bottom_y + 3)
    g.add_edge("ENTRANCE-0", f"AISLE-{bottom}-0")
    g.add_node("ENTRANCE-1", right_x, bottom_y + 3)
    g.add_edge("ENTRANCE-1", f"AISLE-{bottom}-{last_i}")

    g.add_node("EXIT-0", left_x, -3)
    g.add_edge("EXIT-0", "AISLE-0-0")
    g.add_node("EXIT-1", right_x, -3)
    g.add_edge("EXIT-1", f"AISLE-0-{last_i}")

    # 5) UI çizimi için geometri
    g.geom = {
        "stop_count": len(stops),
        "h_roads": [(f"AISLE-{a}-0", f"AISLE-{a}-{last_i}") for a in range(n_aisles)],
        "v_roads": [(f"AISLE-0-{i}", f"AISLE-{n_aisles - 1}-{i}") for i in road_indices],
        "gate_roads": [
            ("ENTRANCE-0", f"AISLE-{bottom}-0"),
            ("ENTRANCE-1", f"AISLE-{bottom}-{last_i}"),
            ("EXIT-0", "AISLE-0-0"),
            ("EXIT-1", f"AISLE-0-{last_i}"),
        ],
        "entrances": list(ENTRANCES),
        "exits": list(EXITS),
        "x_max": x_max,
    }
    return spots, g


if __name__ == "__main__":
    from collections import Counter
    spots, g = build_parking()
    print(f"Park yeri: {len(spots)} | Graf düğümü: {len(g.nodes())}")
    print(f"Bant: {config.N_BANDS} | Yatay yol: {config.N_AISLES} | "
          f"Blok: {config.N_BLOCKS_X}x{config.BLOCK_W} | Dikey yol: {len(g.geom['v_roads'])}")
    print(f"Giriş: {g.geom['entrances']} | Çıkış: {g.geom['exits']}")
    print("Tip dağılımı:", dict(Counter(s.type for s in spots)))
