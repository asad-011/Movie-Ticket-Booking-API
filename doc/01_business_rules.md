# Movie Ticket Booking API — Requirements & Business Rules

## 1. Overview

A REST API for booking movie tickets. A user browses shows, picks seats, holds
them temporarily, pays (simulated), and can cancel for a time-based refund.
The project exists to be **tested**, not to be a production app — every rule
below is a source of test cases.

## 2. Entities

| Entity | Description |
|---|---|
| Movie | Title, duration, language, genre |
| Show | A screening of a movie at a specific time in a specific screen |
| Seat | One physical seat for a specific show (generated per show) |
| Booking | A reservation of 1+ seats for a show, by one customer |
| Payment | A payment attempt against a booking |

## 3. Core Business Rules

### 3.1 Seats & shows
- A seat belongs to exactly one show (seats are generated fresh when a show is created — no sharing across shows).
- Seat status: `AVAILABLE` → `HELD` → `BOOKED`, or back to `AVAILABLE` on expiry/cancellation.
- A seat can never be held or booked by two bookings at the same time (no double-booking — this is the most important rule to test under concurrency).
- Bookings can only be made for shows where `show_time > now`.
- Seats cannot be modified once a show has started.

### 3.2 Booking limits
- Minimum 1 seat per booking.
- Maximum 6 seats per booking.
- All requested seats must belong to the same show.
- All requested seats must currently be `AVAILABLE`; if even one isn't, the whole booking request fails (no partial booking).

### 3.3 Seat hold & expiry
- When a booking is created, its seats move to `HELD` and the booking gets `hold_expires_at = created_at + 10 minutes`.
- If payment isn't completed before `hold_expires_at`, the booking status becomes `EXPIRED` and its seats return to `AVAILABLE`.
- A background sweep (or a check on every read) enforces expiry — don't rely only on a cron job for your tests; also check-and-expire lazily on access so tests are deterministic.
- Once `EXPIRED`, a booking cannot be paid for. The user must create a new booking.

### 3.4 Pricing
```
subtotal          = sum(seat.price for seat in booked_seats)
convenience_fee   = clamp(subtotal * 2%, min=10, max=50)      # INR
tax               = (subtotal + convenience_fee) * 18%        # GST
discount          = min(coupon_discount, subtotal)            # never exceeds subtotal
total_amount      = subtotal + convenience_fee + tax - discount
total_amount      = max(total_amount, 0)                      # never negative
```
- Round all currency values to 2 decimal places.
- Coupons are out of scope for v1 (see Section 6) but the formula already reserves a slot for `discount` so it's easy to add later.

### 3.5 Payment
- A booking can only be paid while status is `PENDING_PAYMENT` (i.e., seats are `HELD` and not expired).
- Payment is **simulated** via a mock gateway that responds based on a test token sent in the request:

| Test token | Gateway response |
|---|---|
| `tok_success` | Payment succeeds immediately |
| `tok_declined` | Payment fails — card declined |
| `tok_insufficient_funds` | Payment fails — insufficient funds |
| `tok_timeout` | Gateway doesn't respond in time; payment stays `PENDING` |
| any unrecognized token | Treated as `tok_declined` |

- Every pay request must include an `Idempotency-Key` header (a client-generated UUID).
  - First request with a given key: processed normally, result stored against that key.
  - Repeated request with the **same** key: returns the stored result again, without charging or changing state a second time.
  - A different key on an already-`SUCCESS` booking is rejected (`409` — already paid).
- On payment success: booking → `CONFIRMED`, seats → `BOOKED`.
- On payment failure: booking → `PAYMENT_FAILED`, seats return to `AVAILABLE` immediately (don't hold a seat hostage for a failed payment).
- On gateway timeout: booking stays `PENDING_PAYMENT`, seats stay `HELD` (the normal hold-expiry timer still applies — it isn't restarted).

### 3.6 Cancellation & refunds
- Only a `CONFIRMED` booking (i.e., one that was paid) can be cancelled.
- Refund percentage depends on time left before `show_time` at the moment of cancellation:

| Time before show | Refund |
|---|---|
| More than 4 hours | 100% |
| 4 hours or less, but show hasn't started | 50% |
| Show has already started | Cancellation not allowed (`409`) |

- Refund amount = `refund_percentage * total_amount`, rounded to 2 decimals.
- On successful cancellation: booking → `CANCELLED`, seats → `AVAILABLE`, payment → `REFUNDED` (or `PARTIALLY_REFUNDED` for the 50% case).
- A booking cannot be cancelled twice (`409` on the second attempt).
- An unpaid booking (`PENDING_PAYMENT`, `EXPIRED`, `PAYMENT_FAILED`) cannot be "cancelled" — it was never confirmed, so there's nothing to refund. These are abandoned, not cancelled.

### 3.7 Error handling
All errors return a consistent shape:
```json
{
  "error": {
    "code": "SEAT_NOT_AVAILABLE",
    "message": "Seat B4 is already held or booked for this show."
  }
}
```
Suggested codes: `VALIDATION_ERROR`, `SEAT_NOT_AVAILABLE`, `BOOKING_LIMIT_EXCEEDED`, `BOOKING_NOT_FOUND`, `BOOKING_EXPIRED`, `ALREADY_PAID`, `PAYMENT_FAILED`, `SHOW_IN_PAST`, `CANCELLATION_NOT_ALLOWED`, `IDEMPOTENCY_KEY_REQUIRED`.

## 4. Non-functional notes (for your README, not heavy engineering)
- Use UTC internally; accept/return ISO-8601 timestamps.
- Currency: INR, 2 decimal places everywhere.
- No real auth needed for v1 — a `customer_email` field is enough to identify who booked. (You can mention "auth is out of scope, would add JWT in v2" as a deliberate scoping decision in interviews.)

## 5. Explicitly out of scope (v1)
- Coupons/promo codes (formula leaves room for it)
- Multiple screens/theatres management UI
- Real payment gateway integration
- User accounts/login

## 6. Why these rules matter for testing
Each rule above maps to a concrete test category:
- Seat limits (3.2) → boundary value tests (0, 1, 6, 7 seats)
- Hold expiry (3.3) → time-based / state-transition tests
- Pricing (3.4) → calculation tests with fixed inputs and expected outputs
- Payment tokens (3.5) → equivalence partitioning across gateway outcomes
- Idempotency (3.5) → duplicate-request tests
- Refund tiers (3.6) → boundary tests around the 4-hour mark
