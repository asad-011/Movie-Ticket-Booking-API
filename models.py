"""
Database access + business logic for the Movie Ticket Booking API.
Every rule here traces back to 01_business_rules.md.
"""
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import payment_gateway

DB_PATH = os.environ.get("DATABASE_PATH", "movie_booking.db")

HOLD_DURATION_MINUTES = 10
MAX_SEATS_PER_BOOKING = 6
MIN_SEATS_PER_BOOKING = 1
CONVENIENCE_FEE_RATE = 0.02
CONVENIENCE_FEE_MIN = 10.0
CONVENIENCE_FEE_MAX = 50.0
TAX_RATE = 0.18
REFUND_FULL_THRESHOLD_HOURS = 4


class ApiError(Exception):
    """Raised anywhere in the business logic; caught once in app.py."""
    def __init__(self, code, message, status_code):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


# ---------------------------------------------------------------------
# Connection & schema
# ---------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    language TEXT NOT NULL,
    genre TEXT,
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0)
);

CREATE TABLE IF NOT EXISTS shows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_id INTEGER NOT NULL REFERENCES movies(id),
    screen_name TEXT NOT NULL,
    show_time TEXT NOT NULL,
    base_price REAL NOT NULL CHECK (base_price > 0)
);

CREATE TABLE IF NOT EXISTS seats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    show_id INTEGER NOT NULL REFERENCES shows(id),
    seat_number TEXT NOT NULL,
    seat_type TEXT NOT NULL CHECK (seat_type IN ('REGULAR', 'PREMIUM')),
    price REAL NOT NULL CHECK (price > 0),
    status TEXT NOT NULL DEFAULT 'AVAILABLE'
        CHECK (status IN ('AVAILABLE', 'HELD', 'BOOKED')),
    UNIQUE (show_id, seat_number)
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    show_id INTEGER NOT NULL REFERENCES shows(id),
    customer_name TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING_PAYMENT'
        CHECK (status IN ('PENDING_PAYMENT','CONFIRMED','CANCELLED','EXPIRED','PAYMENT_FAILED')),
    subtotal REAL NOT NULL,
    convenience_fee REAL NOT NULL,
    tax REAL NOT NULL,
    discount REAL NOT NULL DEFAULT 0,
    total_amount REAL NOT NULL,
    hold_expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS booking_seats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL REFERENCES bookings(id),
    seat_id INTEGER NOT NULL REFERENCES seats(id)
    -- No UNIQUE(seat_id) here: a seat is reused across many bookings over its
    -- lifetime (book -> cancel -> book again). Preventing double-booking is
    -- already handled by the atomic status check in create_booking(), which
    -- only moves a seat to HELD if its current status is AVAILABLE.
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL REFERENCES bookings(id),
    amount REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','SUCCESS','FAILED','REFUNDED','PARTIALLY_REFUNDED')),
    gateway_token TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    refund_amount REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def init_db(seed=False):
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    if seed:
        _seed(conn)
    conn.close()


def _seed(conn):
    cur = conn.execute("SELECT COUNT(*) AS n FROM movies")
    if cur.fetchone()["n"] > 0:
        conn.close()
        return  # already seeded

    conn.execute(
        "INSERT INTO movies (title, language, genre, duration_minutes) VALUES "
        "('Pathaan 2','Hindi','Action',150), ('Interstellar','English','Sci-Fi',169)"
    )
    conn.execute(
        "INSERT INTO shows (movie_id, screen_name, show_time, base_price) VALUES "
        "(1,'Screen 1','2027-01-15T18:30:00Z',200.0), "
        "(2,'Screen 2','2027-01-15T21:00:00Z',250.0)"
    )
    seats = [(1, f"A{i}", "PREMIUM", 300.0) for i in range(1, 6)] + \
            [(1, f"B{i}", "REGULAR", 200.0) for i in range(1, 6)]
    conn.executemany(
        "INSERT INTO seats (show_id, seat_number, seat_type, price, status) "
        "VALUES (?, ?, ?, ?, 'AVAILABLE')",
        seats,
    )
    conn.commit()


# ---------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------
def now_utc():
    return datetime.now(timezone.utc)


def now_iso():
    return now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------
# Movies & shows
# ---------------------------------------------------------------------
def list_movies():
    conn = get_db()
    rows = conn.execute("SELECT * FROM movies").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_shows(movie_id=None):
    conn = get_db()
    if movie_id:
        rows = conn.execute("SELECT * FROM shows WHERE movie_id = ?", (movie_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM shows").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_show_or_404(conn, show_id):
    row = conn.execute("SELECT * FROM shows WHERE id = ?", (show_id,)).fetchone()
    if not row:
        raise ApiError("SHOW_NOT_FOUND", f"Show {show_id} does not exist.", 404)
    return dict(row)


def list_seats_for_show(show_id):
    conn = get_db()
    get_show_or_404(conn, show_id)  # 404s if missing
    rows = conn.execute("SELECT * FROM seats WHERE show_id = ?", (show_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------
# Pricing (business_rules.md section 3.4)
# ---------------------------------------------------------------------
def compute_pricing(seat_rows, discount=0.0):
    subtotal = sum(s["price"] for s in seat_rows)
    convenience_fee = min(max(subtotal * CONVENIENCE_FEE_RATE, CONVENIENCE_FEE_MIN), CONVENIENCE_FEE_MAX)
    tax = (subtotal + convenience_fee) * TAX_RATE
    discount = min(discount, subtotal)
    total = max(subtotal + convenience_fee + tax - discount, 0)
    return {
        "subtotal": round(subtotal, 2),
        "convenience_fee": round(convenience_fee, 2),
        "tax": round(tax, 2),
        "discount": round(discount, 2),
        "total_amount": round(total, 2),
    }


# ---------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------
def create_booking(show_id, customer_name, customer_email, seat_ids):
    if not seat_ids or not (MIN_SEATS_PER_BOOKING <= len(seat_ids) <= MAX_SEATS_PER_BOOKING):
        raise ApiError(
            "BOOKING_LIMIT_EXCEEDED",
            f"A booking must contain between {MIN_SEATS_PER_BOOKING} and {MAX_SEATS_PER_BOOKING} seats.",
            422,
        )
    if len(set(seat_ids)) != len(seat_ids):
        raise ApiError("VALIDATION_ERROR", "Duplicate seat_ids in request.", 422)

    conn = get_db()
    show = get_show_or_404(conn, show_id)
    if parse_iso(show["show_time"]) <= now_utc():
        conn.close()
        raise ApiError("SHOW_IN_PAST", "Cannot book a show that has already started.", 409)

    placeholders = ",".join("?" * len(seat_ids))
    seat_rows = conn.execute(
        f"SELECT * FROM seats WHERE id IN ({placeholders})", seat_ids
    ).fetchall()
    seat_rows = [dict(r) for r in seat_rows]

    if len(seat_rows) != len(seat_ids):
        conn.close()
        raise ApiError("VALIDATION_ERROR", "One or more seat_ids do not exist.", 422)
    if any(s["show_id"] != show_id for s in seat_rows):
        conn.close()
        raise ApiError("VALIDATION_ERROR", "All seats must belong to the same show.", 422)

    try:
        conn.execute("BEGIN IMMEDIATE")
        updated = conn.execute(
            f"UPDATE seats SET status = 'HELD' "
            f"WHERE id IN ({placeholders}) AND status = 'AVAILABLE'",
            seat_ids,
        )
        if updated.rowcount != len(seat_ids):
            conn.execute("ROLLBACK")
            conn.close()
            raise ApiError(
                "SEAT_NOT_AVAILABLE",
                "One or more requested seats are already held or booked.",
                409,
            )

        pricing = compute_pricing(seat_rows)
        created = now_iso()
        expires = (now_utc() + timedelta(minutes=HOLD_DURATION_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")

        cur = conn.execute(
            "INSERT INTO bookings (show_id, customer_name, customer_email, status, "
            "subtotal, convenience_fee, tax, discount, total_amount, "
            "hold_expires_at, created_at, updated_at) "
            "VALUES (?, ?, ?, 'PENDING_PAYMENT', ?, ?, ?, ?, ?, ?, ?, ?)",
            (show_id, customer_name, customer_email, pricing["subtotal"],
             pricing["convenience_fee"], pricing["tax"], pricing["discount"],
             pricing["total_amount"], expires, created, created),
        )
        booking_id = cur.lastrowid

        conn.executemany(
            "INSERT INTO booking_seats (booking_id, seat_id) VALUES (?, ?)",
            [(booking_id, sid) for sid in seat_ids],
        )
        conn.commit()
    finally:
        conn.close()

    return get_booking(booking_id)


def _release_seats(conn, booking_id):
    conn.execute(
        "UPDATE seats SET status = 'AVAILABLE' WHERE id IN "
        "(SELECT seat_id FROM booking_seats WHERE booking_id = ?)",
        (booking_id,),
    )


def get_booking(booking_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if not row:
        conn.close()
        raise ApiError("BOOKING_NOT_FOUND", f"Booking {booking_id} does not exist.", 404)
    booking = dict(row)

    # Lazy expiry — see business_rules.md section 3.3
    if booking["status"] == "PENDING_PAYMENT" and parse_iso(booking["hold_expires_at"]) <= now_utc():
        conn.execute(
            "UPDATE bookings SET status = 'EXPIRED', updated_at = ? WHERE id = ?",
            (now_iso(), booking_id),
        )
        _release_seats(conn, booking_id)
        conn.commit()
        booking["status"] = "EXPIRED"

    seat_rows = conn.execute(
        "SELECT seats.seat_number FROM seats "
        "JOIN booking_seats ON booking_seats.seat_id = seats.id "
        "WHERE booking_seats.booking_id = ?",
        (booking_id,),
    ).fetchall()
    booking["seats"] = [r["seat_number"] for r in seat_rows]

    payment_row = conn.execute(
        "SELECT * FROM payments WHERE booking_id = ? ORDER BY id DESC LIMIT 1",
        (booking_id,),
    ).fetchone()
    booking["payment"] = dict(payment_row) if payment_row else None

    conn.close()
    return booking


# ---------------------------------------------------------------------
# Payments (business_rules.md section 3.5)
# ---------------------------------------------------------------------
def process_payment(booking_id, idempotency_key, gateway_token):
    if not idempotency_key:
        raise ApiError("IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header is required.", 400)

    conn = get_db()

    # Idempotent replay: same key -> same stored result, no side effects.
    existing = conn.execute(
        "SELECT * FROM payments WHERE idempotency_key = ?", (idempotency_key,)
    ).fetchone()
    if existing:
        conn.close()
        booking = get_booking(booking_id)
        return {
            "booking_id": booking_id,
            "booking_status": booking["status"],
            "payment_status": existing["status"],
            "amount_charged": existing["amount"] if existing["status"] == "SUCCESS" else 0,
        }

    booking_row = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if not booking_row:
        conn.close()
        raise ApiError("BOOKING_NOT_FOUND", f"Booking {booking_id} does not exist.", 404)
    booking = dict(booking_row)

    if booking["status"] == "CONFIRMED":
        conn.close()
        raise ApiError("ALREADY_PAID", "This booking has already been paid for.", 409)

    # Trigger lazy expiry check via get_booking, then re-check status.
    conn.close()
    booking = get_booking(booking_id)
    if booking["status"] != "PENDING_PAYMENT":
        raise ApiError(
            "BOOKING_EXPIRED" if booking["status"] == "EXPIRED" else "ALREADY_PAID",
            f"Booking is in status {booking['status']} and cannot be paid for.",
            409,
        )

    outcome = payment_gateway.charge(gateway_token)
    created = now_iso()

    conn = get_db()
    conn.execute(
        "INSERT INTO payments (booking_id, amount, status, gateway_token, "
        "idempotency_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (booking_id, booking["total_amount"], outcome, gateway_token,
         idempotency_key, created, created),
    )

    if outcome == "SUCCESS":
        conn.execute(
            "UPDATE bookings SET status = 'CONFIRMED', updated_at = ? WHERE id = ?",
            (created, booking_id),
        )
        conn.execute(
            "UPDATE seats SET status = 'BOOKED' WHERE id IN "
            "(SELECT seat_id FROM booking_seats WHERE booking_id = ?)",
            (booking_id,),
        )
    elif outcome == "FAILED":
        conn.execute(
            "UPDATE bookings SET status = 'PAYMENT_FAILED', updated_at = ? WHERE id = ?",
            (created, booking_id),
        )
        _release_seats(conn, booking_id)
    # PENDING (gateway timeout): booking stays PENDING_PAYMENT, seats stay HELD.

    conn.commit()
    conn.close()

    return {
        "booking_id": booking_id,
        "booking_status": "CONFIRMED" if outcome == "SUCCESS"
            else "PAYMENT_FAILED" if outcome == "FAILED"
            else "PENDING_PAYMENT",
        "payment_status": outcome,
        "amount_charged": booking["total_amount"] if outcome == "SUCCESS" else 0,
    }


# ---------------------------------------------------------------------
# Cancellation & refunds (business_rules.md section 3.6)
# ---------------------------------------------------------------------
def cancel_booking(booking_id):
    booking = get_booking(booking_id)  # applies lazy expiry first

    if booking["status"] != "CONFIRMED":
        raise ApiError(
            "CANCELLATION_NOT_ALLOWED",
            f"Booking in status {booking['status']} cannot be cancelled.",
            409,
        )

    conn = get_db()
    show = get_show_or_404(conn, booking["show_id"])
    show_time = parse_iso(show["show_time"])
    now = now_utc()

    if show_time <= now:
        conn.close()
        raise ApiError("CANCELLATION_NOT_ALLOWED", "The show has already started.", 409)

    hours_before = (show_time - now).total_seconds() / 3600
    refund_pct = 100 if hours_before > REFUND_FULL_THRESHOLD_HOURS else 50
    refund_amount = round(booking["total_amount"] * refund_pct / 100, 2)
    payment_status = "REFUNDED" if refund_pct == 100 else "PARTIALLY_REFUNDED"
    ts = now_iso()

    conn.execute(
        "UPDATE bookings SET status = 'CANCELLED', updated_at = ? WHERE id = ?",
        (ts, booking_id),
    )
    _release_seats(conn, booking_id)
    conn.execute(
        "UPDATE payments SET status = ?, refund_amount = ?, updated_at = ? "
        "WHERE booking_id = ? AND status = 'SUCCESS'",
        (payment_status, refund_amount, ts, booking_id),
    )
    conn.commit()
    conn.close()

    return {
        "booking_id": booking_id,
        "booking_status": "CANCELLED",
        "payment_status": payment_status,
        "refund_amount": refund_amount,
        "refund_percentage": refund_pct,
    }
