"""
server.py — Web görselleştirme katmanı (FastAPI + WebSocket).

Backend (MQTT, SQLite, A*, Gemini) aynen korunur; bu katman yalnızca görseli
tarayıcıya taşır:
- GET  /              -> tek sayfa arayüz (HTML/Canvas)
- GET  /api/layout    -> statik otopark yerleşimi (yerler, yollar, kapılar, yol grafı)
- GET  /api/state     -> anlık doluluk + sayılar
- WS   /ws            -> canlı doluluk akışı (her ~0.5 sn)
- POST /api/request   -> doğal dil isteği -> orchestrator -> {reply, result, params}

Çalıştırma:
    python -m web.server         (sonra tarayıcıda http://127.0.0.1:8000)
"""

import os
import asyncio
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

import time

import config
from algorithm.graph import build_parking, ENTRANCES
from algorithm import allocator
from backend import database, parking_state, anomaly, analytics, predict, log
from llm import orchestrator
from simulator import sensor_simulator
from backend import mqtt_client

logger = log.get(__name__)

# Aktif rezervasyonlar: spot_id -> son geçerlilik zamanı (sweeper süresi dolanı düşürür).
# Birden çok thread (istek işleyicileri + sweeper) erişir -> kilitle koru (race önle).
_RESERVATIONS = {}
_RES_LOCK = threading.Lock()

# Statik yerleşim/graf bir kez kurulur (doluluk DB'den canlı gelir)
_SPOTS, _GRAPH = build_parking()
_POS = {n: _GRAPH.position(n) for n in _GRAPH.nodes()}

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _seg(n1, n2):
    x1, y1 = _POS[n1]
    x2, y2 = _POS[n2]
    return [x1, y1, x2, y2]


def _spot_access(spot_id):
    """Bir park yerinin bağlı olduğu koridor (aisle) düğümü."""
    for m, _ in _GRAPH.neighbors(spot_id):
        if m.startswith("AISLE"):
            return m
    return None


def _layout_payload():
    """Tarayıcının çizeceği statik her şey: yerler, yollar, kapılar, AVM, yol grafı."""
    geom = _GRAPH.geom
    spots = [{"id": s.id, "x": s.x, "y": s.y, "type": s.type, "zone": s.zone,
              "face": s.face, "section": s.id.split("-")[0], "access": _spot_access(s.id)}
             for s in _SPOTS]
    roads = {
        "h": [_seg(a, b) for a, b in geom["h_roads"]],
        "v": [_seg(a, b) for a, b in geom["v_roads"]],
        "gates": [_seg(a, b) for a, b in geom["gate_roads"]],
    }

    xs = [p[0] for p in _POS.values()]
    ys = [p[1] for p in _POS.values()]
    spot_xs = [s.x for s in _SPOTS]
    # AVM binası: üst cephede, kapıların üstünde (çizim alanını da yukarı genişletir)
    mall = {"x0": min(spot_xs) - 1.0, "x1": max(spot_xs) + 1.0, "y0": -7.5, "y1": -1.5}
    bounds = {"min_x": min(xs) - 0.5, "max_x": max(xs) + 0.5,
              "min_y": mall["y0"] - 0.5, "max_y": max(ys) + 0.5}

    # Trafik için yol grafı (yol düğümleri: aisle + tüm kapılar)
    def is_road(n):
        return (n.startswith("AISLE") or n.startswith("ENTRANCE")
                or n.startswith("VEXIT") or n.startswith("MALL"))

    road_nodes = {n: [_POS[n][0], _POS[n][1]] for n in _GRAPH.nodes() if is_road(n)}
    road_adj = {n: [m for m, _ in _GRAPH.neighbors(n) if m in road_nodes]
                for n in road_nodes}

    return {
        "spots": spots, "roads": roads, "mall": mall, "bounds": bounds,
        "entrances": geom["entrances_geom"],
        "vexits": geom["vexits_geom"],
        "doors": geom["doors_geom"],
        "sections": geom["sections"],
        "islands": geom["islands"],
        "road_nodes": road_nodes, "road_adj": road_adj,
    }


def _state_payload():
    spots = parking_state.get_state()
    occupancy = {s["id"]: s["occupied"] for s in spots}
    # Rezerve yerler: id -> KALAN saniye (UI'da geri sayım gösterir)
    now = time.time()
    with _RES_LOCK:
        reserved = {sid: max(0, int(exp - now)) for sid, exp in _RESERVATIONS.items()}
    occ = sum(1 for v in occupancy.values() if v)
    res = len(reserved)
    total = len(spots)
    sim = sensor_simulator.SIM_STATE
    anom = anomaly.detect()
    edge = sensor_simulator.EDGE_STATS
    return {"occupancy": occupancy,
            "reserved": reserved,
            "counts": {"total": total, "occupied": occ, "reserved": res,
                       "empty": total - occ - res},
            "sim": {"hour": sim["hour"], "busy": sim["busy"]},
            "sensors": anomaly.health_summary(),
            "gateway": {"online": mqtt_client.GATEWAY_STATE["online"]},
            "anomalies": anom["counts"],
            "edge": {"filtered": edge["filtered"], "confirmed": edge["confirmed"]}}


def _reservation_sweeper(stop):
    """Süresi dolan ya da araç gelip park edilen rezervasyonları temizler."""
    while not stop.is_set():
        now = time.time()
        with _RES_LOCK:
            items = list(_RESERVATIONS.items())
        for sid, expire in items:
            spot = database.get_spot(sid)
            if spot is None or spot["occupied"] or not spot["reserved"] or now > expire:
                # Süre doldu ya da araç park etti (set_occupied reserved'i zaten kaldırır)
                if spot is not None and spot["reserved"] and not spot["occupied"]:
                    database.set_reserved(sid, False)
                with _RES_LOCK:
                    _RESERVATIONS.pop(sid, None)
        stop.wait(2.0)


@asynccontextmanager
async def lifespan(app):
    # Backend thread'lerini başlat (sensör simülatörü + MQTT abonesi + rezervasyon sweeper)
    database.init_db()
    stop = threading.Event()
    threads = [
        threading.Thread(target=mqtt_client.start_subscriber, args=(stop,), daemon=True),
        threading.Thread(target=sensor_simulator.run_simulator, args=(stop,), daemon=True),
        threading.Thread(target=_reservation_sweeper, args=(stop,), daemon=True),
    ]
    for t in threads:
        t.start()
    app.state.stop = stop
    logger.info("Sunucu hazır -> http://127.0.0.1:8000")
    yield
    stop.set()


app = FastAPI(lifespan=lifespan)


class ParkRequest(BaseModel):
    text: str
    entrance: str | None = None


class VehicleRequest(BaseModel):
    vehicle_type: str = "normal"
    preference: str = "any"
    needs_charging: bool = False
    duration_hours: int | None = None
    entrance: str | None = None


class MultiRequest(BaseModel):
    requests: list[VehicleRequest]


@app.get("/")
def index():
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))


@app.get("/api/layout")
def layout():
    return _layout_payload()


@app.get("/api/state")
def state():
    return _state_payload()


@app.get("/api/anomalies")
def anomalies():
    """Sensör/durum anomalileri (takılı sensör, çevrimdışı, düşük pil) + filo özeti."""
    out = anomaly.detect()
    out["sensors"] = anomaly.health_summary()
    out["gateway"] = {"online": mqtt_client.GATEWAY_STATE["online"]}
    return out


@app.get("/api/analytics")
def analytics_endpoint():
    """Doluluk zaman serisi, ortalama kalış, bölge yoğunluğu, ısı haritası."""
    return analytics.summary()


class ReserveRequest(BaseModel):
    spot_id: str


@app.post("/api/reserve")
def reserve(req: ReserveRequest):
    """Bir yeri gelmeden ayırt (rezerve). Dolu/zaten rezerve ise reddedilir."""
    spot = database.get_spot(req.spot_id)
    if spot is None:
        return {"ok": False, "reason": "Yer bulunamadı."}
    if spot["occupied"]:
        return {"ok": False, "reason": "Yer dolu, rezerve edilemez."}
    if spot["reserved"]:
        return {"ok": False, "reason": "Bu yer zaten rezerve."}
    database.set_reserved(req.spot_id, True)
    with _RES_LOCK:
        _RESERVATIONS[req.spot_id] = time.time() + config.RESERVATION_TIMEOUT_SEC
    return {"ok": True, "spot_id": req.spot_id,
            "timeout_sec": config.RESERVATION_TIMEOUT_SEC}


@app.post("/api/cancel_reservation")
def cancel_reservation(req: ReserveRequest):
    database.set_reserved(req.spot_id, False)
    with _RES_LOCK:
        _RESERVATIONS.pop(req.spot_id, None)
    return {"ok": True, "spot_id": req.spot_id}


@app.get("/api/predict")
def predict_endpoint(horizon_min: int = 15):
    """Yakın gelecek doluluk tahmini (öngörücü zekâ)."""
    return predict.predict(horizon_min=horizon_min)


@app.get("/api/assignments")
def assignments_endpoint(limit: int = 50):
    """Son yönlendirme kararları (karar/oturum logu — denetim izi)."""
    return {"assignments": database.get_assignments(limit)}


@app.post("/api/request")
def do_request(req: ParkRequest):
    entrance = req.entrance if req.entrance in ENTRANCES else None
    out = orchestrator.handle_request(req.text, entrance=entrance)
    result = out["result"]
    if result:
        result = dict(result)
        # Düğüm yolunu tarayıcının çizebilmesi için koordinat listesine çevir
        result["path_points"] = [[_POS[n][0], _POS[n][1]] for n in result["path"]]
    return {"reply": out["reply"], "result": result,
            "params": out["params"], "source": out["source"]}


@app.post("/api/request_multi")
def do_request_multi(req: MultiRequest):
    """Çoklu araç OPTIMAL atama (G2.4 / Hungarian).

    Aynı anda gelen birden çok aracı çakışmadan en uygun yerlere dağıtır;
    her sonuç tarayıcının çizebilmesi için path_points (koordinat) içerir."""
    reqs = []
    for v in req.requests:
        entrance = v.entrance if v.entrance in ENTRANCES else None
        reqs.append({"vehicle_type": v.vehicle_type, "preference": v.preference,
                     "needs_charging": v.needs_charging,
                     "duration_hours": v.duration_hours, "entrance": entrance})

    assigned = allocator.allocate_multiple(reqs)
    results, total = [], 0.0
    for res in assigned:
        if res:
            total += res["distance"]
            results.append({
                "spot_id": res["spot_id"], "spot_type": res["spot"]["type"],
                "distance": res["distance"], "walk_to_exit": res["walk_to_exit"],
                "path_points": [[_POS[n][0], _POS[n][1]] for n in res["path"]],
            })
        else:
            results.append(None)
    return {"results": results, "total_distance": round(total, 2)}


@app.websocket("/ws")
async def ws_state(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(_state_payload())
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


if __name__ == "__main__":
    uvicorn.run("web.server:app", host="127.0.0.1", port=8000, reload=False)
