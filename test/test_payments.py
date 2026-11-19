"""Payment and idempotency tests. TC IDs reference 05_test_cases.xlsx."""
import pytest
from conftest import force_hold_expired, book_and_pay


@pytest.mark.parametrize("token,expected_status,expected_booking_status", [
    ("tok_success", 200, "CONFIRMED"),              # TC-28
    ("tok_declined", 402, "PAYMENT_FAILED"),        # TC-29
    ("tok_insufficient_funds", 402, "PAYMENT_FAILED"),  # TC-30
    ("tok_timeout", 200, "PENDING_PAYMENT"),        # TC-31
    ("tok_garbage_unrecognized", 402, "PAYMENT_FAILED"),  # TC-32
])
def test_gateway_outcomes(client, future_show, token, expected_status, expected_booking_status):
    show = future_show()
    seat = show["seat_ids"][0]
    booking = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": [seat],
    }).get_json()

    resp = client.post(
        f"/bookings/{booking['id']}/pay",
        json={"gateway_token": token},
        headers={"Idempotency-Key": "key-1"},
    )
    assert resp.status_code == expected_status
    assert resp.get_json()["booking_status"] == expected_booking_status


def test_tc33_pay_without_idempotency_key_rejected(client, future_show):
    show = future_show()
    booking = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": [show["seat_ids"][0]],
    }).get_json()

    resp = client.post(f"/bookings/{booking['id']}/pay", json={"gateway_token": "tok_success"})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_tc34_paying_already_confirmed_booking_rejected(client, future_show):
    show = future_show()
    booking_id, _ = book_and_pay(client, show["show_id"], [show["seat_ids"][0]], idem_key="key-a")

    resp = client.post(
        f"/bookings/{booking_id}/pay",
        json={"gateway_token": "tok_success"},
        headers={"Idempotency-Key": "key-b"},  # a different key
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "ALREADY_PAID"


def test_tc35_paying_expired_booking_rejected(client, future_show):
    show = future_show()
    booking = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": [show["seat_ids"][0]],
    }).get_json()
    force_hold_expired(booking["id"])

    resp = client.post(
        f"/bookings/{booking['id']}/pay",
        json={"gateway_token": "tok_success"},
        headers={"Idempotency-Key": "key-1"},
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "BOOKING_EXPIRED"


def test_tc36_paying_nonexistent_booking_rejected(client):
    resp = client.post(
        "/bookings/999999/pay",
        json={"gateway_token": "tok_success"},
        headers={"Idempotency-Key": "key-1"},
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "BOOKING_NOT_FOUND"


def test_tc37_replaying_same_idempotency_key_returns_same_result(client, future_show):
    show = future_show()
    booking_id, first = book_and_pay(client, show["show_id"], [show["seat_ids"][0]], idem_key="dup-key")
    assert first.get_json()["payment_status"] == "SUCCESS"

    replay = client.post(
        f"/bookings/{booking_id}/pay",
        json={"gateway_token": "tok_success"},
        headers={"Idempotency-Key": "dup-key"},  # same key
    )
    assert replay.status_code == 200
    assert replay.get_json()["payment_status"] == "SUCCESS"

    # No double charge: only one payment row should exist for this booking.
    import models
    conn = models.get_db()
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM payments WHERE booking_id = ?", (booking_id,)
    ).fetchone()["n"]
    conn.close()
    assert count == 1
