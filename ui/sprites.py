"""
sprites.py — Üstten görünüm araç çizimi ve yer ikonları.

Performans için araç görselleri bir kez üretilip (renk + boyut) önbelleğe alınır;
hareketli araçlar için belirli açılarda döndürülmüş kopyalar da önbelleklenir.
Taban araç görseli SAĞA bakar (+x); açı = atan2(-dy, dx) ile yöne döndürülür.
"""

import math

import pygame

# (length, width, color) -> taban yüzey (sağa bakar)
_base_cache = {}
# (length, width, color, angle_bucket) -> döndürülmüş yüzey
_rot_cache = {}


def _darken(color, f=0.6):
    return (int(color[0] * f), int(color[1] * f), int(color[2] * f))


def _make_base(length, width, color):
    """Sağa bakan (nose=+x) üstten görünüm araç yüzeyi üret (tekerlek, kabin, cam)."""
    length = max(int(length), 14)
    width = max(int(width), 8)
    # Üst-alta tekerleklerin taşması için biraz pay bırak (yükseklik = width + 4)
    pad = 3
    surf = pygame.Surface((length, width + 2 * pad), pygame.SRCALPHA)
    L, W = length, width
    top = pad

    # Tekerlekler (gövdenin biraz dışına taşar)
    tyre = (24, 24, 28)
    wl, wh = max(int(L * 0.22), 4), max(int(W * 0.16), 3)
    for wx in (int(L * 0.14), int(L * 0.66)):
        pygame.draw.rect(surf, tyre, (wx, top - pad + 1, wl, wh), border_radius=2)            # üst
        pygame.draw.rect(surf, tyre, (wx, top + W - wh + pad - 1, wl, wh), border_radius=2)   # alt

    # Gövde
    body = pygame.Rect(0, top + int(W * 0.08), L, int(W * 0.84))
    radius = max(int(W * 0.34), 3)
    pygame.draw.rect(surf, color, body, border_radius=radius)
    pygame.draw.rect(surf, _darken(color, 0.5), body, width=1, border_radius=radius)
    # Kaput çizgisi (parlama)
    pygame.draw.rect(surf, _darken(color, 1.25 if max(color) < 200 else 0.85),
                     (int(L * 0.30), top + int(W * 0.2), int(L * 0.40), int(W * 0.6)),
                     border_radius=2)

    # Camlar
    glass = (180, 206, 230)
    pygame.draw.rect(surf, glass,                      # ön cam (sağ)
                     (int(L * 0.60), top + int(W * 0.18), int(L * 0.14), int(W * 0.64)),
                     border_radius=2)
    pygame.draw.rect(surf, _darken(glass, 0.85),        # arka cam (sol)
                     (int(L * 0.24), top + int(W * 0.2), int(L * 0.12), int(W * 0.6)),
                     border_radius=2)

    # Farlar (ön = sağ uç) ve stop lambaları (arka = sol uç)
    pygame.draw.rect(surf, (255, 246, 190), (L - 2, top + int(W * 0.14), 2, int(W * 0.22)))
    pygame.draw.rect(surf, (255, 246, 190), (L - 2, top + int(W * 0.64), 2, int(W * 0.22)))
    pygame.draw.rect(surf, (210, 60, 50), (0, top + int(W * 0.14), 2, int(W * 0.22)))
    pygame.draw.rect(surf, (210, 60, 50), (0, top + int(W * 0.64), 2, int(W * 0.22)))
    return surf


def get_car(length, width, color, angle_deg):
    """Verilen renk/boyut/açıya göre döndürülmüş araç yüzeyini (önbellekli) döndür."""
    length, width = int(length), int(width)
    base_key = (length, width, color)
    base = _base_cache.get(base_key)
    if base is None:
        base = _make_base(length, width, color)
        _base_cache[base_key] = base

    bucket = int(round(angle_deg / 8.0)) * 8        # 8°'lik kovalar -> önbellek küçük kalır
    key = (length, width, color, bucket)
    rot = _rot_cache.get(key)
    if rot is None:
        rot = pygame.transform.rotate(base, bucket)
        _rot_cache[key] = rot
    return rot


def draw_car(surface, center, color, length, width, angle_deg):
    """Aracı merkez noktasına, yönüne dönmüş olarak çiz."""
    sprite = get_car(length, width, color, angle_deg)
    rect = sprite.get_rect(center=(int(center[0]), int(center[1])))
    surface.blit(sprite, rect)


def heading_from_velocity(dx, dy, fallback=0.0):
    """Hız vektöründen derece cinsinden yön (taban sağa baktığı için atan2(-dy, dx))."""
    if dx * dx + dy * dy < 1e-6:
        return fallback
    return math.degrees(math.atan2(-dy, dx))


# ---------------------------------------------------------------------------
# Yer ikonları (boş özel park yerleri için zemine çizilir)
# ---------------------------------------------------------------------------
def draw_ev_icon(surface, rect, color=(250, 225, 55)):
    """Şarj yeri: küçük şimşek (yıldırım) simgesi."""
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2
    s = min(w, h) * 0.32
    pts = [
        (cx + s * 0.15, cy - s),
        (cx - s * 0.45, cy + s * 0.15),
        (cx - s * 0.02, cy + s * 0.15),
        (cx - s * 0.15, cy + s),
        (cx + s * 0.45, cy - s * 0.15),
        (cx + s * 0.02, cy - s * 0.15),
    ]
    pygame.draw.polygon(surface, color, pts)


def draw_disabled_icon(surface, rect, color=(235, 240, 250)):
    """Engelli yeri: basit tekerlekli sandalye benzeri simge."""
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2
    r = max(int(min(w, h) * 0.28), 4)
    # baş
    pygame.draw.circle(surface, color, (int(cx), int(cy - r * 0.9)), max(int(r * 0.32), 2))
    # tekerlek
    pygame.draw.circle(surface, color, (int(cx), int(cy + r * 0.35)), r, 2)
