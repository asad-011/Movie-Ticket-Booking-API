# Test Plan — Movie Ticket Booking API

## 1. Objective
Validate that the Movie Ticket Booking API correctly implements the rules in
`01_business_rules.md`, focusing on booking limits, seat-hold/expiry logic,
pricing, payment state transitions (including idempotency), and
cancellation/refund calculations.

## 2. Scope

**In scope**
- `GET /movies`, `GET /shows`, `GET /shows/<id>/seats`
- `POST /bookings` (creation, validation, seat holding)
- `GET /bookings/<id>` (including lazy hold-expiry)
- `POST /bookings/<id>/pay` (all gateway outcomes, idempotency)
- `DELETE /bookings/<id>` (cancellation, refund tiers)
- Data integrity: seat status transitions, pricing calculations, booking/payment status consistency

**Out of scope**
- Load/performance testing
- Real payment gateway integration
- Authentication/authorization (none exists in v1)
- UI/frontend (API only)

## 3. Test Approach

| Level | Method | Tool |
|---|---|---|
| Manual exploratory | Hand-run requests to probe behavior before automating | curl / Postman |
| Functional (API) | Positive, negative, and boundary test cases against each endpoint | Postman collection |
| Automated regression | Same test cases, scripted and repeatable | pytest + `requests` |
| Data verification | Confirm DB state (seat status, totals) matches API responses | SQL queries inside pytest |
| CI | Run the full suite on every push | GitHub Actions |

## 4. Test Environment
- Local Flask dev server (`python app.py`), SQLite file DB, reset to a known seed state before each test run.
- Python 3.x, `pytest`, `requests`, `pytest-html` for reporting.
- Postman + Newman for collection-based runs.

## 5. Entry Criteria
- `app.py` runs without errors and `GET /health` returns 200.
- Seed data (movies, shows, seats) loads successfully.

## 6. Exit Criteria
- All Priority-1 (critical) test cases pass.
- No open defects of Severity "Critical" or "High".
- Automated suite is green in CI.

## 7. Risks & Assumptions
- Seat-hold expiry (10 minutes) is time-dependent — tests simulate this by manipulating `hold_expires_at` directly in the DB rather than waiting 10 real minutes.
- SQLite's `BEGIN IMMEDIATE` is assumed sufficient to prevent double-booking under this app's single-process dev setup; genuine concurrent-load testing is out of scope for v1.
- Dates in seed data are fixed at a distant future date — if the project runs past that date, seed data will need refreshing.

## 8. Test Case Categories (see `05_test_cases.xlsx`)
1. Movie & show browsing
2. Booking creation — validation & limits
3. Seat availability & double-booking
4. Pricing calculation
5. Payment — gateway outcomes
6. Payment — idempotency
7. Cancellation & refund tiers
8. Error handling / response shape

## 9. Deliverables
- This test plan
- `05_test_cases.xlsx` — 45 documented test cases
- Postman collection (`movie_booking_api.postman_collection.json`)
- pytest automated suite (Phase 4)
- Bug reports for any defects found (Phase 6)
