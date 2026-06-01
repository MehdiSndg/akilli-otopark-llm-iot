"""
pygame_app.py — Ana pencere, döngü ve çizim (gerçekçi otopark görselleştirmesi).

Sol panel: AVM otoparkı — bloklu park cepleri (beyaz şeritli), aralarında asfalt
yollar (yatay + dikey) + sarı kesikli şeritler, dolu yerlerde üstten görünüm
araçlar, yollarda SÜREKLİ dolaşan ambient trafik (kapılara da gider) ve birden
fazla giriş/çıkış. Sağ panel: sohbet.

Sürücü metin yazıp gönderince orchestrator AYRI THREAD'de çağrılır (UI donmaz);
dönen yer sarı yanıp söner ve yönlendirilen araç en yakın girişten A* rotası
boyunca yönüne dönerek o yere sürer.

Çalıştırma:
    python -m ui.pygame_app
"""

import math
import queue
import threading

import pygame

import config
from algorithm.graph import build_parking, ENTRANCES
from backend import database, parking_state
from llm import orchestrator
from ui import layout, widgets, sprites


def _start_backend():
    from simulator import sensor_simulator
    from backend import mqtt_client
    stop = threading.Event()
    threads = [
        threading.Thread(target=mqtt_client.start_subscriber, args=(stop,), daemon=True),
        threading.Thread(target=sensor_simulator.run_simulator, args=(stop,), daemon=True),
    ]
    for t in threads:
        t.start()
    return stop, threads


# ---------------------------------------------------------------------------
# Hareket
# ---------------------------------------------------------------------------
class CarAnimation:
    def __init__(self, points, speed=260.0):
        self.points = points
        self.speed = speed
        self.seg = 0
        self.t = 0.0
        self.done = len(points) < 2

    def update(self, dt):
        if self.done:
            return
        remaining = self.speed * dt
        while remaining > 0 and self.seg < len(self.points) - 1:
            ax, ay = self.points[self.seg]
            bx, by = self.points[self.seg + 1]
            seg_len = math.hypot(bx - ax, by - ay)
            if seg_len < 1e-6:
                self.seg += 1
                self.t = 0.0
                continue
            if self.t + remaining >= seg_len:
                remaining -= (seg_len - self.t)
                self.seg += 1
                self.t = 0.0
            else:
                self.t += remaining
                remaining = 0.0
        if self.seg >= len(self.points) - 1:
            self.done = True

    def position(self):
        if self.seg >= len(self.points) - 1:
            return self.points[-1]
        ax, ay = self.points[self.seg]
        bx, by = self.points[self.seg + 1]
        seg_len = math.hypot(bx - ax, by - ay) or 1.0
        f = self.t / seg_len
        return (ax + (bx - ax) * f, ay + (by - ay) * f)


class MovingCar:
    """Rota üzerinde hareket eden, yönüne dönen araç. offset: şeritte sağa kayma."""

    def __init__(self, points, speed, color, length, width, offset=0.0):
        self.anim = CarAnimation(points, speed)
        self.color = color
        self.length = length
        self.width = width
        self.offset = offset
        self.prev = points[0] if points else (0, 0)
        self.angle = 0.0

    def update(self, dt):
        self.anim.update(dt)
        p = self.anim.position()
        self.angle = sprites.heading_from_velocity(p[0] - self.prev[0],
                                                   p[1] - self.prev[1], self.angle)
        self.prev = p

    @property
    def done(self):
        return self.anim.done

    def draw(self, surface):
        p = self.anim.position()
        if self.offset:
            a = math.radians(self.angle)
            hx, hy = math.cos(a), -math.sin(a)         # yön (ekran)
            p = (p[0] - hy * self.offset, p[1] + hx * self.offset)   # sağ şeride kay
        sprites.draw_car(surface, p, self.color, self.length, self.width, self.angle)


# ---------------------------------------------------------------------------
# Çizim
# ---------------------------------------------------------------------------
def _dashed_line(surface, color, p1, p2, width=2, dash=11, gap=9):
    x1, y1 = p1
    x2, y2 = p2
    length = math.hypot(x2 - x1, y2 - y1)
    if length < 1:
        return
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    n = int(length // (dash + gap))
    for i in range(n + 1):
        s = i * (dash + gap)
        e = min(s + dash, length)
        pygame.draw.line(surface, color, (x1 + ux * s, y1 + uy * s),
                         (x1 + ux * e, y1 + uy * e), width)


def _spot_car_color(spot_id):
    h = sum(ord(ch) for ch in spot_id)
    return config.CAR_COLORS[h % len(config.CAR_COLORS)]


def _draw_lot(surface, graph, tf):
    """Otopark zemini + asfalt yollar (geom'dan) + sarı kesikli şeritler."""
    pygame.draw.rect(surface, config.COLOR_LOT_BG, layout.PARKING_RECT, border_radius=10)
    geom = graph.geom
    lane = max(int(tf.scale * config.ROAD_GAP * 0.95), 10)

    def strip(n1, n2):
        pygame.draw.line(surface, config.COLOR_ASPHALT,
                         tf.to_screen(*graph.position(n1)),
                         tf.to_screen(*graph.position(n2)), lane)

    for n1, n2 in geom["gate_roads"]:
        strip(n1, n2)
    for n1, n2 in geom["h_roads"]:
        strip(n1, n2)
    for n1, n2 in geom["v_roads"]:
        strip(n1, n2)
    # Şerit çizgisi yalnızca ana yatay yollarda + ince/nötr (gürültüyü azaltır)
    for n1, n2 in geom["h_roads"]:
        _dashed_line(surface, config.COLOR_LANE,
                     tf.to_screen(*graph.position(n1)),
                     tf.to_screen(*graph.position(n2)), 1, dash=9, gap=12)


def _draw_spots(surface, spots, tf, suggested_id, flash_on):
    """Park ceplerini (beyaz şeritli) çiz; dolu yerlere araç, boş özel yerlere ikon."""
    sw = max(tf.scale * 0.84, 6)
    sh = max(tf.scale * 1.6, 10)
    car_len = max(int(tf.scale * 1.5), 12)
    car_w = max(int(tf.scale * 0.66), 7)

    for s in spots:
        cx, cy = tf.to_screen(s["x"], s["y"])
        rect = pygame.Rect(0, 0, int(sw), int(sh))
        rect.center = (cx, cy)
        upper = (round(s["y"]) % 4) == 1

        pygame.draw.rect(surface, config.COLOR_SLOT, rect, border_radius=2)
        lx, rx, ty, by = rect.left, rect.right, rect.top, rect.bottom
        pygame.draw.line(surface, config.COLOR_PAINT, (lx, ty), (lx, by), 1)
        pygame.draw.line(surface, config.COLOR_PAINT, (rx, ty), (rx, by), 1)
        back_y = by if upper else ty
        pygame.draw.line(surface, config.COLOR_PAINT, (lx, back_y), (rx, back_y), 2)

        if s["occupied"]:
            sprites.draw_car(surface, (cx, cy), _spot_car_color(s["id"]),
                             car_len, car_w, 90 if upper else -90)
        elif s["type"] == "ev_charging":
            pygame.draw.rect(surface, config.COLOR_EV, rect, width=2, border_radius=2)
            sprites.draw_ev_icon(surface, rect)
        elif s["type"] == "disabled":
            pygame.draw.rect(surface, config.COLOR_DISABLED, rect, width=2, border_radius=2)
            sprites.draw_disabled_icon(surface, rect)

        if s["id"] == suggested_id:
            hl = config.COLOR_SUGGESTED if flash_on else (170, 150, 40)
            pygame.draw.rect(surface, hl, rect.inflate(8, 8), width=3, border_radius=4)


def _draw_markers(surface, graph, tf, font):
    """Tüm giriş ve çıkış (AVM kapısı) işaretlerini etiketle."""
    for e in graph.geom["entrances"]:
        x, y = tf.to_screen(*graph.position(e))
        pygame.draw.circle(surface, config.COLOR_ENTRANCE, (x, y), max(int(tf.scale * 0.5), 7))
        lab = font.render("GİRİŞ", True, config.COLOR_ENTRANCE)
        surface.blit(lab, (x - lab.get_width() // 2, y + 7))
    for e in graph.geom["exits"]:
        x, y = tf.to_screen(*graph.position(e))
        pygame.draw.circle(surface, config.COLOR_EXIT, (x, y), max(int(tf.scale * 0.5), 7))
        lab = font.render("ÇIKIŞ", True, config.COLOR_EXIT)
        surface.blit(lab, (x - lab.get_width() // 2, y - 22))


def _draw_stat_cards(surface, x, y, w, num_font, lab_font, total, occ, empty):
    """Üç istatistik kartı (Toplam / Dolu / Boş) — accent şeritli, kart zeminli."""
    gap = 10
    cw = (w - 2 * gap) // 3
    data = [
        ("Toplam", total, config.COLOR_ACCENT),
        ("Dolu", occ, config.COLOR_OCCUPIED),
        ("Boş", empty, config.COLOR_EMPTY),
    ]
    for i, (label, value, accent) in enumerate(data):
        cx = x + i * (cw + gap)
        pygame.draw.rect(surface, config.COLOR_CARD, (cx, y, cw, 56), border_radius=10)
        pygame.draw.rect(surface, accent, (cx, y + 11, 3, 34), border_radius=2)
        surface.blit(num_font.render(str(value), True, config.COLOR_TEXT), (cx + 14, y + 6))
        surface.blit(lab_font.render(label, True, config.COLOR_TEXT_DIM), (cx + 14, y + 34))


def _draw_legend(surface, x, y, w, font):
    items = [
        (config.COLOR_SLOT, "Boş yer", True),
        (config.CAR_COLORS[0], "Dolu (araç)", False),
        (config.COLOR_EV, "Şarjlı (boş)", False),
        (config.COLOR_DISABLED, "Engelli (boş)", False),
        (config.COLOR_SUGGESTED, "Önerilen yer", False),
        (config.COLOR_CAR, "Sizin aracınız", False),
    ]
    col_w = w // 2
    for i, (color, label, outline) in enumerate(items):
        bx = x + (i % 2) * col_w
        by = y + (i // 2) * 22
        box = pygame.Rect(bx, by, 14, 14)
        pygame.draw.rect(surface, color, box, border_radius=3)
        if outline:
            pygame.draw.rect(surface, config.COLOR_PAINT, box, width=1, border_radius=3)
        surface.blit(font.render(label, True, config.COLOR_TEXT_DIM), (bx + 20, by - 1))


# ---------------------------------------------------------------------------
# Ana uygulama
# ---------------------------------------------------------------------------
def run(start_backend=True, max_frames=None):
    database.init_db()
    stop_event, _threads = (_start_backend() if start_backend else (None, []))

    pygame.init()
    pygame.display.set_caption("Akıllı Otopark Yönlendirme — LLM + IoT")
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("segoeui,arial,dejavusans", 18)
    small = pygame.font.SysFont("segoeui,arial,dejavusans", 14)
    title_font = pygame.font.SysFont("segoeui,arial,dejavusans", 22, bold=True)

    _, graph = build_parking()
    tf = layout.build_transform(graph)

    cx, cy, cw, ch = layout.CHAT_RECT
    ix, iw = cx + 18, cw - 36
    input_box = widgets.InputBox((cx + 10, cy + ch - 50, cw - 130, 40), font)
    send_btn = widgets.Button((cx + cw - 110, cy + ch - 50, 100, 40), font, "Gönder")
    entrance_sel = widgets.Segmented(
        (ix, cy + 224, iw, 32), small,
        [("Sol giriş", ENTRANCES[0]), ("Sağ giriş", ENTRANCES[1])],
    )
    chat = widgets.ChatLog(small)
    chat.add("info", "Merhaba! Nasıl bir park yeri istediğinizi yazın.")
    chat.add("info", "Örn: \"Elektrikli arabam var, çıkışa yakın bir yer istiyorum\".")

    spots_state = parking_state.get_state()
    suggested_id = None
    path_points = []
    assigned_car = None
    result_queue = queue.Queue()
    processing = False
    refresh_timer = 0.0
    car_len = max(int(tf.scale * 1.7), 14)
    car_w = max(int(tf.scale * 0.78), 8)

    def submit(text):
        nonlocal processing
        processing = True
        input_box.enabled = send_btn.enabled = False
        entrance = entrance_sel.value
        side = entrance_sel.options[entrance_sel.selected][0]
        chat.add("user", f"{text}  ({side})")
        chat.add("info", "Düşünüyor...")

        def worker():
            try:
                out = orchestrator.handle_request(text, entrance=entrance)
            except Exception as e:
                out = {"error": str(e)}
            result_queue.put(out)

        threading.Thread(target=worker, daemon=True).start()

    running = True
    frames = 0
    while running:
        dt = clock.tick(config.FPS) / 1000.0
        frames += 1
        flash_on = pygame.time.get_ticks() % 800 < 400

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            entrance_sel.handle_event(event)
            submitted = input_box.handle_event(event)
            if submitted and not processing:
                submit(submitted)
            if send_btn.clicked(event) and input_box.text.strip() and not processing:
                submit(input_box.text.strip())
                input_box.text = ""

        try:
            out = result_queue.get_nowait()
        except queue.Empty:
            out = None
        if out is not None:
            processing = False
            input_box.enabled = send_btn.enabled = True
            if "error" in out:
                chat.add("system", f"Hata oluştu: {out['error']}")
                suggested_id, path_points, assigned_car = None, [], None
            else:
                chat.add("system", out["reply"])
                result = out["result"]
                if result:
                    suggested_id = result["spot_id"]
                    path_points = [tf.to_screen(*graph.position(n)) for n in result["path"]]
                    assigned_car = MovingCar(path_points, 240, config.COLOR_CAR, car_len, car_w)
                else:
                    suggested_id, path_points, assigned_car = None, [], None

        refresh_timer += dt
        if refresh_timer >= 0.5:
            refresh_timer = 0.0
            spots_state = parking_state.get_state()

        if assigned_car:
            assigned_car.update(dt)

        # --- Çizim ---
        screen.fill(config.COLOR_BG)
        _draw_lot(screen, graph, tf)
        _draw_spots(screen, spots_state, tf, suggested_id, flash_on)
        if path_points:
            pygame.draw.lines(screen, config.COLOR_PATH, False, path_points, 3)
        _draw_markers(screen, graph, tf, small)
        if assigned_car:
            assigned_car.draw(screen)

        pygame.draw.rect(screen, config.COLOR_PANEL, layout.CHAT_RECT, border_radius=14)
        total, occ, empty = parking_state.summary()
        # Başlık + accent nokta
        pygame.draw.circle(screen, config.COLOR_ACCENT, (ix + 5, cy + 26), 5)
        screen.blit(title_font.render("Otopark Asistanı", True, config.COLOR_TEXT),
                    (ix + 18, cy + 15))
        screen.blit(small.render("LLM + IoT yönlendirme", True, config.COLOR_TEXT_DIM),
                    (ix + 18, cy + 44))
        _draw_stat_cards(screen, ix, cy + 74, iw, title_font, small, total, occ, empty)
        _draw_legend(screen, ix, cy + 132, iw, small)
        screen.blit(small.render("Hangi kapıdan girdiniz?", True, config.COLOR_TEXT_DIM),
                    (ix, cy + 202))
        entrance_sel.draw(screen)
        chat.draw(screen, (cx + 6, cy + 264, cw - 12, ch - 264 - 64))
        input_box.placeholder = "Düşünüyor..." if processing else "Mesajınızı yazın..."
        input_box.draw(screen)
        send_btn.draw(screen)

        pygame.display.flip()
        if max_frames is not None and frames >= max_frames:
            running = False

    if stop_event:
        stop_event.set()
    pygame.quit()


if __name__ == "__main__":
    run()
