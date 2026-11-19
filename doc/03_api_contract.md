# Movie Ticket Booking API — API Contract

Base URL: `http://127.0.0.1:5000`
All request/response bodies are JSON. All timestamps are ISO-8601 UTC.
Error shape is always:
```json
{ "error": { "code": "SEAT_NOT_AVAILABLE", "message": "Seat B4 is already held or booked." } }
```

---

## 1. GET /movies
List all movies.

**200 OK**
```json
[
  { "id": 1, "title": "Pathaan 2", "language": "Hindi", "genre": "Action", "duration_minutes": 150 }
]
```

## 2. GET /shows?movie_id=<id>
List shows, optionally filtered by movie.

**200 OK**
```json
[
  { "id": 1, "movie_id": 1, "screen_name": "Screen 1", "show_time": "2027-01-15T18:30:00Z", "base_price": 200.0 }
]
```

## 3. GET /shows/<show_id>/seats
Seat map for a show.

**200 OK**
```json
{
  "show_id": 1,
  "seats": [
    { "id": 1, "seat_number": "A1", "seat_type": "PREMIUM", "price": 300.0, "status": "AVAILABLE" },
    { "id": 6, "seat_number": "B1", "seat_type": "REGULAR", "price": 200.0, "status": "HELD" }
  ]
}
```
**404** if show doesn't exist → `code: SHOW_NOT_FOUND`

---

## 4. POST /bookings
Create a booking (holds seats for 10 minutes).

**Request**
```json
{
  "show_id": 1,
  "customer_name": "Riya Sharma",
  "customer_email": "riya@example.com",
  "seat_ids": [1, 2]
}
```

**201 Created**
```json
{
  "id": 101,
  "show_id": 1,
  "status": "PENDING_PAYMENT",
  "seats": ["A1", "A2"],
  "subtotal": 600.0,
  "convenience_fee": 12.0,
  "tax": 110.16,
  "discount": 0,
  "total_amount": 722.16,
  "hold_expires_at": "2026-11-19T10:40:00Z",
  "created_at": "2026-11-19T10:30:00Z"
}
```

**Error cases**
| Condition | Status | Code |
|---|---|---|
| `seat_ids` empty or > 6 items | 422 | `BOOKING_LIMIT_EXCEEDED` |
| Any seat not `AVAILABLE` | 409 | `SEAT_NOT_AVAILABLE` |
| Seats belong to different shows | 422 | `VALIDATION_ERROR` |
| `show_time` is in the past | 409 | `SHOW_IN_PAST` |
| Missing/invalid fields | 400 | `VALIDATION_ERROR` |
| `show_id` doesn't exist | 404 | `SHOW_NOT_FOUND` |

---

## 5. GET /bookings/<booking_id>
Fetch a booking. If `hold_expires_at` has passed and status is still
`PENDING_PAYMENT`, the API lazily flips it to `EXPIRED` and releases seats
before responding — this keeps expiry deterministic for tests.

**200 OK** — same shape as the POST response, plus `payment` (null until a payment exists).

**404** → `BOOKING_NOT_FOUND`

---

## 6. POST /bookings/<booking_id>/pay
Attempt payment for a booking. Requires `Idempotency-Key` header.

**Headers**
```
Idempotency-Key: 6b1f2e3a-... (client-generated UUID)
```

**Request**
```json
{ "gateway_token": "tok_success" }
```

**200 OK (success)**
```json
{
  "booking_id": 101,
  "booking_status": "CONFIRMED",
  "payment_status": "SUCCESS",
  "amount_charged": 722.16
}
```

**200 OK (gateway timeout — booking stays pending)**
```json
{
  "booking_id": 101,
  "booking_status": "PENDING_PAYMENT",
  "payment_status": "PENDING",
  "amount_charged": 0
}
```

**402 Payment Required (declined / insufficient funds)**
```json
{ "error": { "code": "PAYMENT_FAILED", "message": "Card declined." } }
```
→ booking status becomes `PAYMENT_FAILED`, seats return to `AVAILABLE`.

**Error cases**
| Condition | Status | Code |
|---|---|---|
| Missing `Idempotency-Key` header | 400 | `IDEMPOTENCY_KEY_REQUIRED` |
| Booking already `CONFIRMED` | 409 | `ALREADY_PAID` |
| Booking `EXPIRED` | 409 | `BOOKING_EXPIRED` |
| Same `Idempotency-Key` replayed | 200 | returns the original stored result, no side effects |
| `booking_id` doesn't exist | 404 | `BOOKING_NOT_FOUND` |

---

## 7. DELETE /bookings/<booking_id>
Cancel a confirmed booking and compute the refund.

**200 OK**
```json
{
  "booking_id": 101,
  "booking_status": "CANCELLED",
  "payment_status": "REFUNDED",
  "refund_amount": 722.16,
  "refund_percentage": 100
}
```

**Error cases**
| Condition | Status | Code |
|---|---|---|
| Booking not `CONFIRMED` (never paid) | 409 | `CANCELLATION_NOT_ALLOWED` |
| Already `CANCELLED` | 409 | `CANCELLATION_NOT_ALLOWED` |
| Show has already started | 409 | `CANCELLATION_NOT_ALLOWED` |
| `booking_id` doesn't exist | 404 | `BOOKING_NOT_FOUND` |

---

## Status code conventions used throughout
- `200` success (read, or write with no new resource)
- `201` resource created
- `400` malformed request (bad JSON, missing required field)
- `404` resource not found
- `409` conflict with current state (seat taken, already paid, already cancelled)
- `422` semantically invalid (seat count out of range, cross-show seats)
- `402` payment failed

This table itself is good interview material — be ready to explain *why* you
chose 409 vs 422 for a given case.
