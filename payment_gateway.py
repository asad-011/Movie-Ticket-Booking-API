"""
Mock payment gateway.

Real gateways are out of scope for this project (see 01_business_rules.md,
section 5). This module simulates one deterministically, based on a
"test token" the client sends — the same pattern Stripe's own test cards use.
"""

# token -> outcome. Anything not in this dict is treated as DECLINED.
TOKEN_OUTCOMES = {
    "tok_success": "SUCCESS",
    "tok_declined": "FAILED",
    "tok_insufficient_funds": "FAILED",
    "tok_timeout": "PENDING",
}


def charge(token: str) -> str:
    """
    Simulate sending a charge request to a payment gateway.
    Returns one of: "SUCCESS", "FAILED", "PENDING".
    """
    return TOKEN_OUTCOMES.get(token, "FAILED")
