-- Movie Ticket Booking API — SQLite schema
-- Matches 01_business_rules.md. Run with: sqlite3 movie_booking.db < 02_database_schema.sql

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- MOVIES
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS movies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    language        TEXT NOT NULL,
    genre           TEXT,
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- SHOWS  (a screening of a movie at a specific time)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shows (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_id        INTEGER NOT NULL REFERENCES movies(id),
    screen_name     TEXT NOT NULL,            -- e.g. "Screen 1"
    show_time       TEXT NOT NULL,             -- ISO-8601 UTC, e.g. 2026-12-01T18:30:00Z
    base_price      REAL NOT NULL CHECK (base_price > 0),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- SEATS  (generated per show when the show is created — not shared)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS seats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    show_id         INTEGER NOT NULL REFERENCES shows(id),
    seat_number     TEXT NOT NULL,             -- e.g. "A1", "F10"
    seat_type       TEXT NOT NULL CHECK (seat_type IN ('REGULAR', 'PREMIUM')),
    price           REAL NOT NULL CHECK (price > 0),
    status          TEXT NOT NULL DEFAULT 'AVAILABLE'
                      CHECK (status IN ('AVAILABLE', 'HELD', 'BOOKED')),
    UNIQUE (show_id, seat_number)
);

-- ---------------------------------------------------------------------
-- BOOKINGS
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bookings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    show_id           INTEGER NOT NULL REFERENCES shows(id),
    customer_name     TEXT NOT NULL,
    customer_email    TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'PENDING_PAYMENT'
                        CHECK (status IN (
                          'PENDING_PAYMENT', 'CONFIRMED', 'CANCELLED',
                          'EXPIRED', 'PAYMENT_FAILED'
                        )),
    subtotal          REAL NOT NULL,
    convenience_fee   REAL NOT NULL,
    tax               REAL NOT NULL,
    discount          REAL NOT NULL DEFAULT 0,
    total_amount      REAL NOT NULL,
    hold_expires_at   TEXT NOT NULL,          -- created_at + 10 minutes
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- BOOKING_SEATS  (many-to-many: a booking can cover 1-6 seats)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS booking_seats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id  INTEGER NOT NULL REFERENCES bookings(id),
    seat_id     INTEGER NOT NULL REFERENCES seats(id),
    UNIQUE (seat_id)   -- a seat can only ever belong to ONE active booking row
);

-- ---------------------------------------------------------------------
-- PAYMENTS
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id        INTEGER NOT NULL REFERENCES bookings(id),
    amount            REAL NOT NULL,
    status            TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN (
                          'PENDING', 'SUCCESS', 'FAILED',
                          'REFUNDED', 'PARTIALLY_REFUNDED'
                        )),
    gateway_token     TEXT,                  -- e.g. tok_success, tok_declined
    idempotency_key   TEXT NOT NULL UNIQUE,
    refund_amount     REAL,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- Helpful indexes
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_seats_show_id ON seats(show_id);
CREATE INDEX IF NOT EXISTS idx_bookings_show_id ON bookings(show_id);
CREATE INDEX IF NOT EXISTS idx_payments_booking_id ON payments(booking_id);
CREATE INDEX IF NOT EXISTS idx_payments_idempotency_key ON payments(idempotency_key);

-- ---------------------------------------------------------------------
-- Seed data (for local dev / manual Postman testing)
-- ---------------------------------------------------------------------
INSERT INTO movies (title, language, genre, duration_minutes) VALUES
  ('Pathaan 2', 'Hindi', 'Action', 150),
  ('Interstellar', 'English', 'Sci-Fi', 169);

-- Show far enough in the future that your tests won't suddenly start failing
INSERT INTO shows (movie_id, screen_name, show_time, base_price) VALUES
  (1, 'Screen 1', '2027-01-15T18:30:00Z', 200.0),
  (2, 'Screen 2', '2027-01-15T21:00:00Z', 250.0);

-- 10 seats for show 1: A1-A5 (PREMIUM), B1-B5 (REGULAR)
INSERT INTO seats (show_id, seat_number, seat_type, price, status) VALUES
  (1, 'A1', 'PREMIUM', 300.0, 'AVAILABLE'),
  (1, 'A2', 'PREMIUM', 300.0, 'AVAILABLE'),
  (1, 'A3', 'PREMIUM', 300.0, 'AVAILABLE'),
  (1, 'A4', 'PREMIUM', 300.0, 'AVAILABLE'),
  (1, 'A5', 'PREMIUM', 300.0, 'AVAILABLE'),
  (1, 'B1', 'REGULAR', 200.0, 'AVAILABLE'),
  (1, 'B2', 'REGULAR', 200.0, 'AVAILABLE'),
  (1, 'B3', 'REGULAR', 200.0, 'AVAILABLE'),
  (1, 'B4', 'REGULAR', 200.0, 'AVAILABLE'),
  (1, 'B5', 'REGULAR', 200.0, 'AVAILABLE');
