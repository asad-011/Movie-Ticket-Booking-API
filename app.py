"""
Movie Ticket Booking API — Flask app.
Routes map 1:1 to 03_api_contract.md. All business logic lives in models.py.
"""
import os
from flask import Flask, request, jsonify

import models

app = Flask(__name__)


@app.errorhandler(models.ApiError)
def handle_api_error(err):
    return jsonify({"error": {"code": err.code, "message": err.message}}), err.status_code


@app.errorhandler(400)
def handle_bad_request(err):
    return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "Malformed request body."}}), 400


def require_fields(body, fields):
    missing = [f for f in fields if f not in body or body[f] in (None, "")]
    if missing:
        raise models.ApiError(
            "VALIDATION_ERROR", f"Missing required field(s): {', '.join(missing)}.", 400
        )


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.get("/movies")
def get_movies():
    return jsonify(models.list_movies()), 200


@app.get("/shows")
def get_shows():
    movie_id = request.args.get("movie_id", type=int)
    return jsonify(models.list_shows(movie_id)), 200


@app.get("/shows/<int:show_id>/seats")
def get_show_seats(show_id):
    seats = models.list_seats_for_show(show_id)
    return jsonify({"show_id": show_id, "seats": seats}), 200


@app.post("/bookings")
def post_booking():
    body = request.get_json(silent=True) or {}
    require_fields(body, ["show_id", "customer_name", "customer_email", "seat_ids"])
    booking = models.create_booking(
        show_id=body["show_id"],
        customer_name=body["customer_name"],
        customer_email=body["customer_email"],
        seat_ids=body["seat_ids"],
    )
    return jsonify(booking), 201


@app.get("/bookings/<int:booking_id>")
def get_booking(booking_id):
    return jsonify(models.get_booking(booking_id)), 200


@app.post("/bookings/<int:booking_id>/pay")
def pay_booking(booking_id):
    idempotency_key = request.headers.get("Idempotency-Key")
    body = request.get_json(silent=True) or {}
    require_fields(body, ["gateway_token"])
    result = models.process_payment(booking_id, idempotency_key, body["gateway_token"])
    status_code = 402 if result["payment_status"] == "FAILED" else 200
    return jsonify(result), status_code


@app.delete("/bookings/<int:booking_id>")
def delete_booking(booking_id):
    result = models.cancel_booking(booking_id)
    return jsonify(result), 200


if __name__ == "__main__":
    # Fresh local DB with seed data if one doesn't already exist.
    if not os.path.exists(models.DB_PATH):
        models.init_db(seed=True)
    else:
        models.init_db(seed=False)
    app.run(debug=True, port=5000)
