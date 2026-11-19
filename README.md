Movie Ticket Booking API & Automation Framework

A RESTful movie ticket booking application built using Python, Flask, and SQLite, with a focus on API testing and automation.

This project simulates a movie ticket booking workflow and uses pytest to validate API behaviour across booking, payment, cancellation, and pricing operations.

The project demonstrates practical knowledge of REST API testing, test case design, automated testing, database validation, and defect identification.

Key Features

Movie Booking: API functionality for managing movie ticket bookings.

Payment Simulation: Simulated payment processing using a separate payment gateway module.

Booking Cancellation: Test scenarios for cancellation workflows.

Pricing Validation: Tests for pricing-related behaviour.

Automated API Testing: pytest-based test suites.

Test Reporting: HTML test report generation.

Manual API Testing: Postman collection for testing API endpoints.

Technology Stack

Technology

Purpose

Python

Backend development

Flask

REST API framework

SQLite

Database

pytest

Automated testing

Postman

Manual API testing

pytest-html

HTML test reports

Git & GitHub

Version control

Project Structure

Movie-ticket-booking-api/
│
├── doc/                     # Project documentation
│
├── postman/                 # Postman collections
│
├── test/
│   ├── conftest.py          # Shared pytest fixtures
│   ├── test_bookings.py     # Booking test cases
│   ├── test_cancellation.py # Cancellation test cases
│   ├── test_payments.py     # Payment test cases
│   └── test_pricing.py      # Pricing test cases
│
├── app.py                   # Flask application
├── models.py                # Database models
├── payment_gateway.py       # Simulated payment gateway
├── movie_booking.db         # SQLite database
├── pytest.ini               # pytest configuration
├── requirements.txt         # Project dependencies
├── report.html              # HTML test report
└── README.md

Getting Started

1. Clone the Repository

git clone https://github.com/asad-011/Movie-ticket-booking-api.git
cd Movie-ticket-booking-api

2. Create a Virtual Environment

python -m venv venv

Activate the environment:

Windows:

venv\Scripts\activate

Linux / macOS:

source venv/bin/activate

3. Install Dependencies

pip install -r requirements.txt

4. Run the Application

python app.py

The Flask application will start on the local development server. Check the terminal for the server address.

Running Automated Tests

Run the complete test suite:

pytest

Run a specific test module:

pytest test/test_bookings.py

Generate an HTML Test Report

pytest --html=report.html --self-contained-html

Open report.html in your browser to view the test execution results.

API Testing with Postman

The postman/ directory contains the Postman collection for manually testing the API.

Open Postman.

Import the collection from the project directory.

Start the Flask application.

Configure the request base URL to match your local server.

Execute the requests and inspect the responses.

Testing Focus

The automated test suite covers the following areas:

Booking functionality

Payment processing

Booking cancellation

Pricing validation

Positive and negative test scenarios

API response validation

Edge-case handling

Project Objective

The objective of this project is to demonstrate how a backend application can be systematically tested using manual and automated testing techniques.

It focuses on designing meaningful test cases, validating API responses, identifying edge cases, and improving application reliability through structured testing.
