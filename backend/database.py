"""
database.py — SQLite şeması ve sorguları.

Park yerlerinin statik bilgisi (id, tip, koordinat, bölge) graph.build_parking()
yerleşiminden tohumlanır; dinamik veriler burada saklanır:
  - spots          : doluluk (occupied), rezervasyon (reserved), son değişim (last_change)
  - sensor_health  : her sensörün sağlığı (batarya, sinyal, çevrimiçi, son görülme)
  - events         : her doluluk değişimi (geçmiş + kalış süresi + anomali için)
  - occupancy_samples : periyodik toplam doluluk örneği (zaman grafiği için)

Eşzamanlılık: simülatör/abone ayrı thread'de yazar, UI okur. Bu yüzden her
işlemde yeni bir bağlantı açılır ve WAL modu kullanılır (eşzamanlı okuma/yazma).
"""

import sqlite3
import random
import hashlib
import time

import config
from algorithm.graph import build_parking

# Şema sürümü: yeni tablo/sütun eklendiğinde artır -> eski DB otomatik tazelenir.
SCHEMA_VERSION = "2"


def _connect():
    conn = sqlite3.connect(config.DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _layout_signature(spots):
    """Yerleşimin imzası: id/koordinat/tip değişirse imza da değişir."""
    h = hashlib.md5()
    for s in spots:
        h.update(f"{s.id},{s.x},{s.y},{s.type},{s.zone};".encode())
    return h.hexdigest()


def _create_tables(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS spots (
            id          TEXT PRIMARY KEY,
            node_id     TEXT    NOT NULL,
            type        TEXT    NOT NULL,
            occupied    INTEGER NOT NULL DEFAULT 0,
            reserved    INTEGER NOT NULL DEFAULT 0,
            last_change REAL    NOT NULL DEFAULT 0,
            x           REAL    NOT NULL,
            y           REAL    NOT NULL,
            zone        TEXT    NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_health (
            spot_id   TEXT PRIMARY KEY,
            battery   REAL    NOT NULL DEFAULT 100,
            rssi      INTEGER NOT NULL DEFAULT -60,
            online    INTEGER NOT NULL DEFAULT 1,
            last_seen REAL    NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            spot_id  TEXT    NOT NULL,
            occupied INTEGER NOT NULL,
            ts       REAL    NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_spot ON events(spot_id, ts)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS occupancy_samples (
            ts       REAL    NOT NULL,
            occupied INTEGER NOT NULL,
            total    INTEGER NOT NULL
        )
        """
    )
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")


def _drop_all(conn):
    for t in ("spots", "sensor_health", "events", "occupancy_samples"):
        conn.execute(f"DROP TABLE IF EXISTS {t}")


def init_db(seed=True, randomize_occupancy=True):
    """Tabloları oluştur; şema sürümü VEYA yerleşim değiştiyse yeniden tohumla.

    - Şema sürümü değişti  -> tüm dinamik tablolar düşürülüp yeniden kurulur.
    - Yerleşim imzası değişti -> spots yeniden tohumlanır (bayat koordinat düzeltme).
    """
    conn = _connect()
    try:
        conn.execute("PRAGMA journal_mode=WAL")

        # Şema sürümü kontrolü (meta tablosu yoksa da güvenli)
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        # Sürüm yok (eski v1 DB) ya da farklı -> dinamik tabloları tazele
        if row is None or row["value"] != SCHEMA_VERSION:
            _drop_all(conn)
        _create_tables(conn)
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                     (SCHEMA_VERSION,))
        conn.commit()

        if seed:
            spots, _ = build_parking()
            sig = _layout_signature(spots)
            count = conn.execute("SELECT COUNT(*) AS n FROM spots").fetchone()["n"]
            row = conn.execute("SELECT value FROM meta WHERE key='layout_sig'").fetchone()
            stored = row["value"] if row else None
            if count == 0 or stored != sig:
                _seed(conn, spots, randomize_occupancy)
                conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('layout_sig', ?)",
                             (sig,))
                conn.commit()
    finally:
        conn.close()


def _seed(conn, spots, randomize_occupancy):
    """Tabloları temizleyip park yerlerini + sensör sağlıklarını yerleşimden tohumla."""
    now = time.time()
    conn.execute("DELETE FROM spots")
    conn.execute("DELETE FROM sensor_health")
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM occupancy_samples")
    spot_rows, health_rows = [], []
    for s in spots:
        occupied = 1 if (randomize_occupancy and
                         random.random() < config.INITIAL_OCCUPANCY_RATE) else 0
        spot_rows.append((s.id, s.node_id, s.type, occupied, 0, now, s.x, s.y, s.zone))
        # Başlangıç sağlığı: dolu batarya, makul sinyal, çevrimiçi
        health_rows.append((s.id, 100.0, random.randint(-72, -48), 1, now))
    conn.executemany(
        "INSERT INTO spots (id, node_id, type, occupied, reserved, last_change, x, y, zone) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        spot_rows,
    )
    conn.executemany(
        "INSERT INTO sensor_health (spot_id, battery, rssi, online, last_seen) "
        "VALUES (?, ?, ?, ?, ?)",
        health_rows,
    )
    conn.commit()


def _row_to_dict(row):
    d = dict(row)
    if "occupied" in d:
        d["occupied"] = bool(d["occupied"])
    if "reserved" in d:
        d["reserved"] = bool(d["reserved"])
    return d


# ---------------------------------------------------------------------------
# Park yeri (doluluk + rezervasyon) okuma/yazma
# ---------------------------------------------------------------------------
def get_all_spots():
    """Tüm park yerlerini (statik + doluluk + rezervasyon) dict listesi döndürür."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM spots ORDER BY id").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_spot(spot_id):
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM spots WHERE id = ?", (spot_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_empty_spots():
    """Boş VE rezerve olmayan park yerleri (gerçekten atanabilir olanlar)."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM spots WHERE occupied = 0 AND reserved = 0 ORDER BY id"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def set_occupied(spot_id, occupied):
    """Doluluğu güncelle. Durum DEĞİŞTİYSE last_change'i tazeler ve olay kaydeder.

    Etkilenen satır sayısını döndürür."""
    conn = _connect()
    try:
        now = time.time()
        row = conn.execute("SELECT occupied, reserved FROM spots WHERE id = ?",
                           (spot_id,)).fetchone()
        if row is None:
            return 0
        new_val = 1 if occupied else 0
        changed = (row["occupied"] != new_val)
        # Araç park edince (dolu oldu) varsa rezervasyonu otomatik kaldır
        clear_res = 1 if (new_val == 1 and row["reserved"]) else 0
        if changed:
            conn.execute(
                "UPDATE spots SET occupied = ?, last_change = ?, "
                "reserved = CASE WHEN ? THEN 0 ELSE reserved END WHERE id = ?",
                (new_val, now, clear_res, spot_id),
            )
            conn.execute("INSERT INTO events (spot_id, occupied, ts) VALUES (?, ?, ?)",
                         (spot_id, new_val, now))
            conn.commit()
            return 1
        return 0
    finally:
        conn.close()


def set_reserved(spot_id, reserved):
    """Rezervasyon bayrağını ayarla. (toplam etkilenen satır)."""
    conn = _connect()
    try:
        cur = conn.execute("UPDATE spots SET reserved = ? WHERE id = ?",
                           (1 if reserved else 0, spot_id))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def counts():
    """(toplam, dolu, boş) — boş = ne dolu ne rezerve."""
    conn = _connect()
    try:
        total = conn.execute("SELECT COUNT(*) AS n FROM spots").fetchone()["n"]
        occ = conn.execute("SELECT COUNT(*) AS n FROM spots WHERE occupied = 1").fetchone()["n"]
        res = conn.execute(
            "SELECT COUNT(*) AS n FROM spots WHERE occupied = 0 AND reserved = 1"
        ).fetchone()["n"]
        return total, occ, total - occ - res
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Sensör sağlığı (telemetri)
# ---------------------------------------------------------------------------
def set_health(spot_id, battery=None, rssi=None, online=None, last_seen=None):
    """Bir sensörün sağlık telemetrisini güncelle (yalnız verilen alanlar)."""
    conn = _connect()
    try:
        ts = float(last_seen) if last_seen is not None else time.time()
        exists = conn.execute("SELECT 1 FROM sensor_health WHERE spot_id = ?",
                              (spot_id,)).fetchone()
        if exists:
            sets, vals = [], []
            if battery is not None:
                sets.append("battery = ?"); vals.append(float(battery))
            if rssi is not None:
                sets.append("rssi = ?"); vals.append(int(rssi))
            if online is not None:
                sets.append("online = ?"); vals.append(1 if online else 0)
            sets.append("last_seen = ?"); vals.append(ts)
            vals.append(spot_id)
            conn.execute(f"UPDATE sensor_health SET {', '.join(sets)} WHERE spot_id = ?", vals)
        else:
            conn.execute(
                "INSERT INTO sensor_health (spot_id, battery, rssi, online, last_seen) "
                "VALUES (?, ?, ?, ?, ?)",
                (spot_id,
                 float(battery) if battery is not None else 100.0,
                 int(rssi) if rssi is not None else -60,
                 1 if (online is None or online) else 0,
                 ts),
            )
        conn.commit()
    finally:
        conn.close()


def get_health():
    """spot_id -> {battery, rssi, online, last_seen} sağlık eşlemesi."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM sensor_health").fetchall()
        out = {}
        for r in rows:
            d = dict(r)
            d["online"] = bool(d["online"])
            out[d["spot_id"]] = d
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Olaylar & örnekler (geçmiş / analitik / anomali)
# ---------------------------------------------------------------------------
def add_sample(occupied, total, ts=None):
    """Periyodik toplam doluluk örneği ekle (zaman grafiği için)."""
    conn = _connect()
    try:
        conn.execute("INSERT INTO occupancy_samples (ts, occupied, total) VALUES (?, ?, ?)",
                     (ts if ts is not None else time.time(), int(occupied), int(total)))
        conn.commit()
    finally:
        conn.close()


def get_samples(limit=240):
    """Son N doluluk örneği (eskiden yeniye)."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT ts, occupied, total FROM occupancy_samples ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


def get_events(limit=2000):
    """Son N doluluk olayı (eskiden yeniye)."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT spot_id, occupied, ts FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


def get_last_changes():
    """spot_id -> last_change (son doluluk değişimi zamanı)."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT id, last_change, occupied FROM spots").fetchall()
        return {r["id"]: {"last_change": r["last_change"], "occupied": bool(r["occupied"])}
                for r in rows}
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    total, occ, empty = counts()
    print(f"DB hazır (şema v{SCHEMA_VERSION}): {total} yer | dolu {occ} | boş {empty}")
