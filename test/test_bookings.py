"""
Booking creation, validation limits, and seat-availability rules.
TC IDs reference 05_test_cases.xlsx.
"""
from conftest import force_hold_expired, book_and_pay


def test_tc06_create_booking_single_seat(client, future_show):
    show = future_show()
    resp = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": [show["seat_ids"][0]],
    })
    assert resp.status_code == 201
    assert resp.get_json()["status"] == "PENDING_PAYMENT"


def test_tc07_create_booking_max_six_seats(client, future_show):
    show = future_show()
    resp = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": show["seat_ids"][:6],
    })
    assert resp.status_code == 201
    assert len(resp.get_json()["seats"]) == 6


def test_tc08_create_booking_zero_seats_rejected(client, future_show):
    show = future_show()
    resp = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": [],
    })
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "BOOKING_LIMIT_EXCEEDED"


def test_tc09_create_booking_seven_seats_rejected(client, future_show):
    show = future_show()
    resp = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": show["seat_ids"][:7],
    })
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "BOOKING_LIMIT_EXCEEDED"


def test_tc10_duplicate_seat_ids_rejected(client, future_show):
    show = future_show()
    seat = show["seat_ids"][0]
    resp = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": [seat, seat],
    })
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_tc11_missing_customer_email_rejected(client, future_show):
    show = future_show()
    resp = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "seat_ids": [show["seat_ids"][0]],
    })
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_tc12_nonexistent_seat_id_rejected(client, future_show):
    show = future_show()
    resp = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": [999999],
    })
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_tc13_seats_from_different_shows_rejected(client, future_show):
    show1 = future_show()
    show2 = future_show()
    resp = client.post("/bookings", json={
        "show_id": show1["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com",
        "seat_ids": [show1["seat_ids"][0], show2["seat_ids"][0]],
    })
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_tc14_booking_for_past_show_rejected(client, future_show):
    show = future_show(hours_from_now=-1)  # already started
    resp = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": [show["seat_ids"][0]],
    })
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "SHOW_IN_PAST"


def test_tc15_nonexistent_show_id_rejected(client):
    resp = client.post("/bookings", json={
        "show_id": 999999, "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": [1],
    })
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "SHOW_NOT_FOUND"


def test_tc17_booking_already_held_seat_rejected(client, future_show):
    show = future_show()
    seat = show["seat_ids"][0]
    first = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": [seat],
    })
    assert first.status_code == 201

    second = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Amit",
        "customer_email": "amit@x.com", "seat_ids": [seat],
    })
    assert second.status_code == 409
    assert second.get_json()["error"]["code"] == "SEAT_NOT_AVAILABLE"


def test_tc18_booking_already_booked_seat_rejected(client, future_show):
    show = future_show()
    seat = show["seat_ids"][0]
    book_and_pay(client, show["show_id"], [seat])

    resp = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Amit",
        "customer_email": "amit@x.com", "seat_ids": [seat],
    })
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "SEAT_NOT_AVAILABLE"


def test_tc20_expired_hold_releases_seat(client, future_show):
    show = future_show()
    seat = show["seat_ids"][0]
    created = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": [seat],
    })
    booking_id = created.get_json()["id"]

    force_hold_expired(booking_id)

    booking_resp = client.get(f"/bookings/{booking_id}")
    assert booking_resp.get_json()["status"] == "EXPIRED"

    seats_resp = client.get(f"/shows/{show['show_id']}/seats")
    seat_data = [s for s in seats_resp.get_json()["seats"] if s["id"] == seat][0]
    assert seat_data["status"] == "AVAILABLE"


def test_tc21_seat_released_on_payment_failure(client, future_show):
    show = future_show()
    seat = show["seat_ids"][0]
    booking_id, pay_resp = book_and_pay(client, show["show_id"], [seat], token="tok_declined")
    assert pay_resp.status_code == 402
    assert pay_resp.get_json()["booking_status"] == "PAYMENT_FAILED"

    seats_resp = client.get(f"/shows/{show['show_id']}/seats")
    seat_data = [s for s in seats_resp.get_json()["seats"] if s["id"] == seat][0]
    assert seat_data["status"] == "AVAILABLE"


def test_tc22_seat_booked_on_payment_success(client, future_show):
    show = future_show()
    seat = show["seat_ids"][0]
    booking_id, pay_resp = book_and_pay(client, show["show_id"], [seat], token="tok_success")
    assert pay_resp.status_code == 200
    assert pay_resp.get_json()["booking_status"] == "CONFIRMED"

    seats_resp = client.get(f"/shows/{show['show_id']}/seats")
    seat_data = [s for s in seats_resp.get_json()["seats"] if s["id"] == seat][0]
    assert seat_data["status"] == "BOOKED"


def test_rebook_seat_after_cancellation_regression(client, future_show):
    """
    Regression test for the UNIQUE(seat_id) bug on booking_seats:
    book -> pay -> cancel -> rebook the SAME seat must succeed (201),
    not crash with a 500.
    """
    show = future_show()
    seat = show["seat_ids"][0]
    booking_id, pay_resp = book_and_pay(client, show["show_id"], [seat])
    assert pay_resp.status_code == 200

    cancel_resp = client.delete(f"/bookings/{booking_id}")
    assert cancel_resp.status_code == 200

    rebook_resp = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Second",
        "customer_email": "second@x.com", "seat_ids": [seat],
    })
    assert rebook_resp.status_code == 201
