"""Cancellation and refund tier tests. TC IDs reference 05_test_cases.xlsx."""
from conftest import book_and_pay


def test_tc40_full_refund_more_than_4_hours_before_show(client, future_show):
    show = future_show(hours_from_now=6)
    booking_id, pay_resp = book_and_pay(client, show["show_id"], [show["seat_ids"][0]])
    assert pay_resp.status_code == 200

    resp = client.delete(f"/bookings/{booking_id}")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["booking_status"] == "CANCELLED"
    assert body["refund_percentage"] == 100
    assert body["payment_status"] == "REFUNDED"


def test_tc41_partial_refund_within_4_hours_of_show(client, future_show):
    show = future_show(hours_from_now=2)
    booking_id, pay_resp = book_and_pay(client, show["show_id"], [show["seat_ids"][0]])
    assert pay_resp.status_code == 200

    resp = client.delete(f"/bookings/{booking_id}")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["refund_percentage"] == 50
    assert body["payment_status"] == "PARTIALLY_REFUNDED"
    assert body["refund_amount"] == round(body.get("refund_amount"), 2)  # sanity: rounded


def test_tc42_cancellation_after_show_started_rejected(client, future_show):
    show = future_show(hours_from_now=1)
    booking_id, pay_resp = book_and_pay(client, show["show_id"], [show["seat_ids"][0]])
    assert pay_resp.status_code == 200

    # Push the show into the past directly (simulates time passing).
    import models
    conn = models.get_db()
    past = models.now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute("UPDATE shows SET show_time = ? WHERE id = ?",
                 ("2020-01-01T00:00:00Z", show["show_id"]))
    conn.commit()
    conn.close()

    resp = client.delete(f"/bookings/{booking_id}")
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CANCELLATION_NOT_ALLOWED"


def test_tc43_cancel_unpaid_booking_rejected(client, future_show):
    show = future_show()
    booking = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": [show["seat_ids"][0]],
    }).get_json()

    resp = client.delete(f"/bookings/{booking['id']}")
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CANCELLATION_NOT_ALLOWED"


def test_tc44_cancel_already_cancelled_booking_rejected(client, future_show):
    show = future_show(hours_from_now=6)
    booking_id, _ = book_and_pay(client, show["show_id"], [show["seat_ids"][0]])
    first = client.delete(f"/bookings/{booking_id}")
    assert first.status_code == 200

    second = client.delete(f"/bookings/{booking_id}")
    assert second.status_code == 409
    assert second.get_json()["error"]["code"] == "CANCELLATION_NOT_ALLOWED"


def test_tc45_seat_available_again_after_cancellation(client, future_show):
    show = future_show(hours_from_now=6)
    seat = show["seat_ids"][0]
    booking_id, _ = book_and_pay(client, show["show_id"], [seat])
    client.delete(f"/bookings/{booking_id}")

    seats_resp = client.get(f"/shows/{show['show_id']}/seats")
    seat_data = [s for s in seats_resp.get_json()["seats"] if s["id"] == seat][0]
    assert seat_data["status"] == "AVAILABLE"
