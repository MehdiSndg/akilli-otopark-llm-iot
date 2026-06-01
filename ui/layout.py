"""
layout.py — Izgara yerleşimi, koordinat dönüşümü ve renkler.

Otopark grafının mantıksal koordinatlarını (x, y) ekran piksellerine çevirir ve
park yeri renk kurallarını sağlar. Pencere iki panele bölünür:
- Sol: otopark görünümü (yollar + park yerleri + araç animasyonu)
- Sağ: sohbet paneli (giriş kutusu + cevap alanı)
"""

import config

# Panel yerleşimi (pikseller)
MARGIN = 16
CHAT_WIDTH = 400

# Sol panel: otopark görünümü
PARKING_RECT = (
    MARGIN, MARGIN,
    config.WINDOW_WIDTH - CHAT_WIDTH - 3 * MARGIN,
    config.WINDOW_HEIGHT - 2 * MARGIN,
)
# Sağ panel: sohbet
CHAT_RECT = (
    config.WINDOW_WIDTH - CHAT_WIDTH - MARGIN, MARGIN,
    CHAT_WIDTH,
    config.WINDOW_HEIGHT - 2 * MARGIN,
)


class Transform:
    """Mantıksal (x, y) -> ekran (px) dönüşümü. Tüm düğümleri panele sığdırır."""

    def __init__(self, positions, rect, pad=46):
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        self.min_x, self.max_x = min(xs), max(xs)
        self.min_y, self.max_y = min(ys), max(ys)

        rx, ry, rw, rh = rect
        world_w = max(self.max_x - self.min_x, 1e-6)
        world_h = max(self.max_y - self.min_y, 1e-6)

        # Hem yatay hem dikey sığacak ölçek (oranı koru)
        self.scale = min((rw - 2 * pad) / world_w, (rh - 2 * pad) / world_h)

        # Çizimi panel içinde ortala
        draw_w = world_w * self.scale
        draw_h = world_h * self.scale
        self.off_x = rx + pad + (rw - 2 * pad - draw_w) / 2
        self.off_y = ry + pad + (rh - 2 * pad - draw_h) / 2

    def to_screen(self, x, y):
        sx = self.off_x + (x - self.min_x) * self.scale
        sy = self.off_y + (y - self.min_y) * self.scale
        return int(sx), int(sy)


def build_transform(graph):
    """Graf düğümlerinin konumlarından bir Transform üretir."""
    positions = [graph.position(n) for n in graph.nodes()]
    return Transform(positions, PARKING_RECT)


def spot_color(spot, occupied, is_suggested, flash_on):
    """
    Bir park yerinin rengini belirle.
    Öncelik: önerilen (yanıp sönen sarı) > dolu (kırmızı) > tip rengi (boş).
    """
    if is_suggested:
        # flash_on True iken parlak sarı, değilken biraz sönük (yanıp sönme)
        return config.COLOR_SUGGESTED if flash_on else (180, 165, 40)
    if occupied:
        return config.COLOR_OCCUPIED
    if spot["type"] == "ev_charging":
        return config.COLOR_EV
    if spot["type"] == "disabled":
        return config.COLOR_DISABLED
    return config.COLOR_EMPTY


# Park yeri kutusunun mantıksal boyutu (1 birim = bir sütun aralığı)
SPOT_W_RATIO = 0.78
SPOT_H_RATIO = 0.78
