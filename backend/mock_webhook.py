#!/usr/bin/env python3
"""
Mocks a Razorpay webhook payload and sends it to the local FastAPI server.
Usage:
    python mock_webhook.py <transaction_id> <decision_id> <status: captured|failed>
"""
import sys
import json
import hmac
import hashlib
import requests

def send_webhook(transaction_id, decision_id, status):
    payload = {
        "entity": "event",
        "account_id": "acc_mock123",
        "event": f"payment.{status}",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_MOCK{transaction_id}{decision_id}",
                    "entity": "payment",
                    "amount": 10000,
                    "currency": "INR",
                    "status": status,
                    "order_id": f"order_{transaction_id}",
                    "invoice_id": None,
                    "international": False,
                    "method": "emandate",
                    "amount_refunded": 0,
                    "refund_status": None,
                    "captured": status == "captured",
                    "description": "Recurring mandate retry",
                    "card_id": None,
                    "bank": "HDFC",
                    "wallet": None,
                    "vpa": None,
                    "email": "customer@example.com",
                    "contact": "+919999999999",
                    "notes": {
                        "transaction_id": transaction_id,
                        "decision_id": decision_id
                    },
                    "fee": 200,
                    "tax": 36,
                    "error_code": None if status == "captured" else "BAD_REQUEST_ERROR",
                    "error_description": None if status == "captured" else "Payment failed at bank",
                    "created_at": 1600000000
                }
            }
        },
        "created_at": 1600000000
    }

    body = json.dumps(payload).encode()
    
    # If the user has a secret set, generate valid HMAC. Else empty.
    import os
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest() if secret else "dummy_signature"

    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": signature
    }

    url = "http://127.0.0.1:8000/webhook/razorpay"
    print(f"Sending {status} webhook for Txn: {transaction_id}, Decision: {decision_id} to {url}")
    
    resp = requests.post(url, data=body, headers=headers)
    print(f"Response: {resp.status_code}")
    print(resp.json())

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python mock_webhook.py <transaction_id> <decision_id> <status: captured|failed>")
        sys.exit(1)
        
    txn_id = sys.argv[1]
    dec_id = sys.argv[2]
    stat = sys.argv[3]
    
    send_webhook(int(txn_id), int(dec_id), stat)
