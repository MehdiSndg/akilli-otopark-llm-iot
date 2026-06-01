"""
parking_state.py — Anlık doluluk durumunu sunan okuma katmanı.

Algoritma (allocator) ve UI doğrudan SQLite/MQTT detaylarıyla uğraşmasın diye
sade bir okuma arayüzü sağlar. Altında database.py vardır.
"""

from backend import database


def get_state():
    """Tüm park yerlerini (doluluk dahil) dict listesi olarak döndürür."""
    return database.get_all_spots()


def get_empty_spots():
    """Yalnızca boş park yerlerini döndürür."""
    return database.get_empty_spots()


def get_state_map():
    """spot_id -> spot dict eşlemesi (UI'da hızlı erişim için)."""
    return {s["id"]: s for s in database.get_all_spots()}


def summary():
    """(toplam, dolu, boş) sayıları."""
    return database.counts()
