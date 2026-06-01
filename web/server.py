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

import config
from algorithm.graph import build_parking, ENTRANCES
from backend import database, parking_state
from llm import orchestrator
from simulator import sensor_simulator
from backend import mqtt_client

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
    occ = sum(1 for v in occupancy.values() if v)
    total = len(spots)
    sim = sensor_simulator.SIM_STATE
    return {"occupancy": occupancy,
            "counts": {"total": total, "occupied": occ, "empty": total - occ},
            "sim": {"hour": sim["hour"], "busy": sim["busy"]}}


@asynccontextmanager
async def lifespan(app):
    # Backend thread'lerini başlat (sensör simülatörü + MQTT abonesi)
    database.init_db()
    stop = threading.Event()
    threads = [
        threading.Thread(target=mqtt_client.start_subscriber, args=(stop,), daemon=True),
        threading.Thread(target=sensor_simulator.run_simulator, args=(stop,), daemon=True),
    ]
    for t in threads:
        t.start()
    app.state.stop = stop
    print("[web] Sunucu hazır -> http://127.0.0.1:8000")
    yield
    stop.set()


app = FastAPI(lifespan=lifespan)


class ParkRequest(BaseModel):
    text: str
    entrance: str | None = None


@app.get("/")
def index():
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))


@app.get("/api/layout")
def layout():
    return _layout_payload()


@app.get("/api/state")
def state():
    return _state_payload()


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
