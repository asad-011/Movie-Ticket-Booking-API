"""Pricing calculation tests. TC IDs reference 05_test_cases.xlsx."""


def test_tc23_subtotal_matches_sum_of_seat_prices(client, future_show):
    show = future_show()
    # First two seats are PREMIUM @ 300 each
    resp = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": show["seat_ids"][:2],
    })
    body = resp.get_json()
    assert body["subtotal"] == 600.0


def test_tc24_convenience_fee_floor_applies(client, future_show):
    show = future_show()
    # One REGULAR seat @ 200 -> 2% = 4.0, below the 10.0 floor
    regular_seat = show["seat_ids"][5]
    resp = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": [regular_seat],
    })
    body = resp.get_json()
    assert body["convenience_fee"] == 10.0


def test_tc26_tax_is_18_percent_of_subtotal_plus_fee(client, future_show):
    show = future_show()
    resp = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": show["seat_ids"][:2],
    })
    body = resp.get_json()
    expected_tax = round((body["subtotal"] + body["convenience_fee"]) * 0.18, 2)
    assert body["tax"] == expected_tax


def test_total_amount_is_sum_of_components(client, future_show):
    show = future_show()
    resp = client.post("/bookings", json={
        "show_id": show["show_id"], "customer_name": "Riya",
        "customer_email": "riya@x.com", "seat_ids": show["seat_ids"][:3],
    })
    body = resp.get_json()
    expected_total = round(
        body["subtotal"] + body["convenience_fee"] + body["tax"] - body["discount"], 2
    )
    assert body["total_amount"] == expected_total
