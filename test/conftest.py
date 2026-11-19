"""
Shared pytest fixtures.

Each test gets a brand-new, isolated SQLite file (via tmp_path) and a fresh
Flask test client — so tests never interfere with each other, and we don't
need to wait real minutes for seat holds to expire or shows to start.
"""
import sys
import os
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import models
import app as app_module


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(models, "DB_PATH", str(db_file))
    models.init_db(seed=True)
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture
def future_show():
    """A show 24 hours from now, with 10 fresh seats (5 PREMIUM @300, 5 REGULAR @200)."""
    def _make(hours_from_now=24):
        conn = models.get_db()
        conn.execute(
            "INSERT INTO movies (title, language, genre, duration_minutes) "
            "VALUES ('Test Movie', 'English', 'Drama', 120)"
        )
        movie_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        show_time = _iso(models.now_utc() + timedelta(hours=hours_from_now))
        conn.execute(
            "INSERT INTO shows (movie_id, screen_name, show_time, base_price) "
            "VALUES (?, 'Screen T', ?, 200.0)",
            (movie_id, show_time),
        )
        show_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        seats = [(show_id, f"P{i}", "PREMIUM", 300.0) for i in range(1, 6)] + \
                [(show_id, f"R{i}", "REGULAR", 200.0) for i in range(1, 6)]
        conn.executemany(
            "INSERT INTO seats (show_id, seat_number, seat_type, price, status) "
            "VALUES (?, ?, ?, ?, 'AVAILABLE')",
            seats,
        )
        conn.commit()
        seat_rows = conn.execute(
            "SELECT id, seat_number FROM seats WHERE show_id = ? ORDER BY id", (show_id,)
        ).fetchall()
        conn.close()
        return {"show_id": show_id, "seat_ids": [r["id"] for r in seat_rows]}
    return _make


def force_hold_expired(booking_id):
    """Back-date a booking's hold so the next read treats it as EXPIRED."""
    conn = models.get_db()
    past = _iso(models.now_utc() - timedelta(minutes=1))
    conn.execute("UPDATE bookings SET hold_expires_at = ? WHERE id = ?", (past, booking_id))
    conn.commit()
    conn.close()


def book_and_pay(client, show_id, seat_ids, token="tok_success", idem_key=None):
    """Helper: create a booking and immediately pay for it. Returns the booking id."""
    resp = client.post("/bookings", json={
        "show_id": show_id, "customer_name": "Test User",
        "customer_email": "test@example.com", "seat_ids": seat_ids,
    })
    assert resp.status_code == 201, resp.get_json()
    booking_id = resp.get_json()["id"]
    resp = client.post(
        f"/bookings/{booking_id}/pay",
        json={"gateway_token": token},
        headers={"Idempotency-Key": idem_key or f"key-{booking_id}"},
    )
    return booking_id, resp
