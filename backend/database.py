"""
database.py — SQLite şeması ve sorguları.

Park yerlerinin statik bilgisi (id, tip, koordinat, bölge) graph.build_parking()
yerleşiminden tohumlanır; dinamik "doluluk" durumu burada saklanır. Sensör
simülatörü MQTT üzerinden doluluğu günceller, algoritma ve UI buradan okur.

Eşzamanlılık: simülatör/abone ayrı thread'de yazar, UI okur. Bu yüzden her
işlemde yeni bir bağlantı açılır ve WAL modu kullanılır (eşzamanlı okuma/yazma).
"""

import sqlite3
import random
import hashlib

import config
from algorithm.graph import build_parking


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


def init_db(seed=True, randomize_occupancy=True):
    """Tabloyu oluştur; boşsa VEYA yerleşim değiştiyse yeniden tohumla.

    Yerleşim (config'teki düzen parametreleri) değiştiğinde eski koordinatlı
    kayıtlar bayatlar; imza karşılaştırmasıyla bunu yakalayıp tabloyu tazeleriz.
    """
    conn = _connect()
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spots (
                id        TEXT PRIMARY KEY,
                node_id   TEXT    NOT NULL,
                type      TEXT    NOT NULL,
                occupied  INTEGER NOT NULL DEFAULT 0,
                x         REAL    NOT NULL,
                y         REAL    NOT NULL,
                zone      TEXT    NOT NULL
            )
            """
        )
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
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
    """Tabloyu temizleyip park yerlerini yerleşimden ekle (başlangıç doluluğu rastgele)."""
    conn.execute("DELETE FROM spots")
    rows = []
    for s in spots:
        occupied = 1 if (randomize_occupancy and
                         random.random() < config.INITIAL_OCCUPANCY_RATE) else 0
        rows.append((s.id, s.node_id, s.type, occupied, s.x, s.y, s.zone))
    conn.executemany(
        "INSERT INTO spots (id, node_id, type, occupied, x, y, zone) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def _row_to_dict(row):
    d = dict(row)
    d["occupied"] = bool(d["occupied"])   # INTEGER 0/1 -> bool
    return d


def get_all_spots():
    """Tüm park yerlerini (statik + doluluk) dict listesi olarak döndürür."""
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
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM spots WHERE occupied = 0 ORDER BY id").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def set_occupied(spot_id, occupied):
    """Bir park yerinin doluluğunu güncelle. Etkilenen satır sayısını döndürür."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE spots SET occupied = ? WHERE id = ?",
            (1 if occupied else 0, spot_id),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def counts():
    """(toplam, dolu, boş) sayıları — hızlı durum kontrolü için."""
    conn = _connect()
    try:
        total = conn.execute("SELECT COUNT(*) AS n FROM spots").fetchone()["n"]
        occ = conn.execute("SELECT COUNT(*) AS n FROM spots WHERE occupied = 1").fetchone()["n"]
        return total, occ, total - occ
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    total, occ, empty = counts()
    print(f"DB hazır: {total} yer | dolu {occ} | boş {empty}")
