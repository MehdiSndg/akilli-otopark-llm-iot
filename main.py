"""
main.py — Her şeyi başlatan giriş noktası (G5.1).

Varsayılan: web arayüzünü (FastAPI + Canvas) başlatır. Sensör simülatörü ve MQTT
abonesi web sunucusunun lifespan'inde ayrı thread'lerde otomatik çalışır; kapanışta
temiz sonlandırılır.

Kullanım:
    python main.py              # web arayüzü -> http://127.0.0.1:8000  (önerilen)
    python main.py --pygame     # alternatif Pygame arayüzü (masaüstü pencere)

Her iki arayüz de aynı backend'i (SQLite + A* + LLM) kullanır.
"""

import sys


def run_web():
    """Web arayüzünü (FastAPI) başlat. Backend thread'leri lifespan'de açılır."""
    import uvicorn
    print("[main] Web arayüzü baslatiliyor -> http://127.0.0.1:8000")
    uvicorn.run("web.server:app", host="127.0.0.1", port=8000, reload=False)


def run_pygame():
    """Alternatif masaüstü Pygame arayüzünü başlat."""
    print("[main] Pygame arayuzu baslatiliyor...")
    from ui import pygame_app
    pygame_app.run()


def main():
    if "--pygame" in sys.argv:
        run_pygame()
    else:
        run_web()


if __name__ == "__main__":
    main()
