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

CATEGORY_TEMPLATE_SIDS = {
    "INSUFFICIENT_FUNDS": "HXabc123insufficient",
    "BANK_OUTAGE": "HXdef456bankoutage",
    "MANDATE_EXPIRED": "HXghi789mandateexpired",
    "MANDATE_CANCELLED": "HXjkl012mandatecancelled",
}

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")


CATEGORY_PREVIEW_TEMPLATES = {
    "INSUFFICIENT_FUNDS": (
        "Hi {name}! Your {merchant} payment of Rs.{amount} on {mandate_date} didn't go "
        "through - looks like the balance was a little short that day. We'll auto-retry "
        "on {recommended_date} when it usually works best for you, or you can pick your "
        "own date."
    ),
    "BANK_OUTAGE": (
        "Hi {name}, your {merchant} payment of Rs.{amount} couldn't be processed because "
        "of a temporary issue at your bank's end - not your fault at all. We'll retry "
        "automatically once your bank is back up."
    ),
    "MANDATE_EXPIRED": (
        "Hi {name}, your Autopay mandate for {merchant} (Rs.{amount}/cycle) has expired, "
        "so we couldn't debit this cycle. Tap the link below to set up a fresh mandate in "
        "under a minute."
    ),
    "MANDATE_CANCELLED": (
        "Hi {name}, it looks like your Autopay mandate for {merchant} was cancelled, so we "
        "couldn't debit this cycle. If that wasn't intentional, tap below to re-enable it."
    ),
}


def build_message_preview(category: str, customer_name: str, merchant: str, amount: float,
                           mandate_date: datetime, recommended_date: datetime) -> str:
    """Renders a human-readable preview of the WhatsApp template for the
    audit trail and merchant dashboard. The real Twilio send always uses
    the approved content_sid + template_vars (see send_nudge) - this is
    display-only, so it never needs Meta approval itself."""
    template = CATEGORY_PREVIEW_TEMPLATES.get(category, CATEGORY_PREVIEW_TEMPLATES["INSUFFICIENT_FUNDS"])
    return template.format(
        name=customer_name,
        merchant=merchant,
        amount=f"{amount:,.0f}",
        mandate_date=mandate_date.strftime("%d %b"),
        recommended_date=recommended_date.strftime("%d %b") if recommended_date else "soon",
    )


def build_template_variables(category: str, customer_name: str, merchant: str, amount: float,
                   mandate_date: datetime, recommended_date: datetime) -> dict:
    """Builds a dictionary of variables mapped to the template's {{1}}, {{2}} placeholders."""
    return {
        "1": customer_name,
        "2": merchant,
        "3": f"{amount:,.0f}",
        "4": mandate_date.strftime("%d %b"),
        "5": recommended_date.strftime("%d %b") if recommended_date else ""
    }


def build_self_schedule_options(recommended_date: datetime) -> list[str]:
    """3 candidate dates centered on the model's recommendation, so the
    customer can nudge the date earlier/later without typing anything."""
    return [
        (recommended_date - timedelta(days=1)).strftime("%Y-%m-%d"),
        recommended_date.strftime("%Y-%m-%d"),
        (recommended_date + timedelta(days=2)).strftime("%Y-%m-%d"),
    ]


def send_nudge(phone: str, category: str, template_vars: dict, channel: str = "whatsapp") -> dict:
    """Sends via Twilio using WhatsApp Content Templates if configured, else simulates. 
    Returns a small result dict for logging/audit purposes."""
    content_sid = CATEGORY_TEMPLATE_SIDS.get(category, CATEGORY_TEMPLATE_SIDS["INSUFFICIENT_FUNDS"])
    
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER:
        try:
            from twilio.rest import Client  # imported lazily; optional dependency
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            to = f"whatsapp:{phone}" if channel == "whatsapp" else phone
            from_ = f"whatsapp:{TWILIO_FROM_NUMBER}" if channel == "whatsapp" else TWILIO_FROM_NUMBER
            msg = client.messages.create(
                content_sid=content_sid,
                content_variables=json.dumps(template_vars),
                from_=from_, 
                to=to
            )
            return {"simulated": False, "sid": msg.sid, "status": msg.status}
        except Exception as exc:  # pragma: no cover - network/optional-dep path
            return {"simulated": True, "error": str(exc)}
    return {
        "simulated": True, 
        "content_sid": content_sid,
        "variables": template_vars,
        "note": "Twilio credentials not configured - simulated template message logged."
    }
