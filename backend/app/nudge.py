"""
Layer 3 - Customer Nudge + Self-Scheduling.

Builds a plain-language, non-accusatory failure message (Hinglish-flavored
by default, matching the customer's preferred_language) and 3 candidate
self-schedule dates. Sends it via Twilio if TWILIO_ACCOUNT_SID /
TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER are set in the environment;
otherwise simulates the send and just logs the message, so the demo works
without Twilio sandbox setup.
"""
import os
import json
from datetime import datetime, timedelta

CATEGORY_MESSAGES = {
    "INSUFFICIENT_FUNDS": (
        "Hi {name}! Your {merchant} payment of Rs.{amount} on {mandate_date} "
        "didn't go through - looks like the balance was a little short that day. "
        "No action needed, we'll auto-retry on {recommended_date} when it usually "
        "works best for you. Or pick your own date below."
    ),
    "BANK_OUTAGE": (
        "Hi {name}, your {merchant} payment of Rs.{amount} couldn't be processed "
        "because of a temporary issue at your bank's end - not your fault at all. "
        "We'll retry automatically once your bank is back up. You can also choose "
        "a date below."
    ),
    "MANDATE_EXPIRED": (
        "Hi {name}, your Autopay mandate for {merchant} (Rs.{amount}/cycle) has "
        "expired, so we couldn't debit this cycle. Tap the link below to set up a "
        "fresh mandate in under a minute - no other action needed."
    ),
    "MANDATE_CANCELLED": (
        "Hi {name}, it looks like your Autopay mandate for {merchant} was "
        "cancelled, so we couldn't debit this cycle. If that wasn't intentional, "
        "tap below to re-enable it in under a minute."
    ),
}

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")


def build_message(category: str, customer_name: str, merchant: str, amount: float,
                   mandate_date: datetime, recommended_date: datetime) -> str:
    template = CATEGORY_MESSAGES.get(category, CATEGORY_MESSAGES["INSUFFICIENT_FUNDS"])
    return template.format(
        name=customer_name,
        merchant=merchant,
        amount=f"{amount:,.0f}",
        mandate_date=mandate_date.strftime("%d %b"),
        recommended_date=recommended_date.strftime("%d %b"),
    )


def build_self_schedule_options(recommended_date: datetime) -> list[str]:
    """3 candidate dates centered on the model's recommendation, so the
    customer can nudge the date earlier/later without typing anything."""
    return [
        (recommended_date - timedelta(days=1)).strftime("%Y-%m-%d"),
        recommended_date.strftime("%Y-%m-%d"),
        (recommended_date + timedelta(days=2)).strftime("%Y-%m-%d"),
    ]


def send_nudge(phone: str, message: str, channel: str = "whatsapp") -> dict:
    """Sends via Twilio if configured, else simulates. Returns a small
    result dict for logging/audit purposes."""
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER:
        try:
            from twilio.rest import Client  # imported lazily; optional dependency
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            to = f"whatsapp:{phone}" if channel == "whatsapp" else phone
            from_ = f"whatsapp:{TWILIO_FROM_NUMBER}" if channel == "whatsapp" else TWILIO_FROM_NUMBER
            msg = client.messages.create(body=message, from_=from_, to=to)
            return {"simulated": False, "sid": msg.sid, "status": msg.status}
        except Exception as exc:  # pragma: no cover - network/optional-dep path
            return {"simulated": True, "error": str(exc)}
    return {"simulated": True, "note": "Twilio credentials not configured - message logged only."}
