"""
log.py — Merkezi loglama yapılandırması (gözlemlenebilirlik).

print yerine seviyeli (INFO/WARNING/ERROR) logging kullanılır; her katman ne
yaptığını [katman] etiketiyle loglar. Böylece sistemin içi görünür olur —
hem hata ayıklama hem sunum için değerli.

Kullanım:
    from backend import log
    logger = log.get(__name__)
    logger.info("broker'a bağlanıldı")

Ortam değişkenleri (.env):
    LOG_LEVEL : DEBUG | INFO | WARNING | ERROR   (varsayılan INFO)
    LOG_FILE  : verilirse loglar bu dosyaya da yazılır (dashboard/inceleme için)
"""

import logging
import os
import sys

_CONFIGURED = False


def setup(level=None):
    """Kök logger'ı bir kez yapılandır (tekrar çağrılırsa yok sayılır)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()

    handlers = [logging.StreamHandler(sys.stdout)]
    log_file = os.getenv("LOG_FILE")
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
    # Üçüncü taraf gürültüsünü kıs (uvicorn/paho zaten ayrı loglar)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _CONFIGURED = True


def get(name):
    """İlgili modül için logger döndür (gerekirse yapılandırmayı başlatır)."""
    setup()
    # Modül adını kısalt: 'backend.mqtt_client' -> 'mqtt_client'
    short = name.rsplit(".", 1)[-1] if name else "app"
    return logging.getLogger(short)
