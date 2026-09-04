from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# In a real system, this would map tokens to a Merchant database table.
# For this demo, we use a simple hardcoded dictionary to simulate Authz.
MOCK_MERCHANT_TOKENS = {
    "secret-vela": "Vela SaaS",
    "secret-securelife": "SecureLife Insurance",
    "secret-growmax": "GrowMax SIP",
    "secret-quickloan": "QuickLoan EMI"
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_merchant(token: str = Depends(oauth2_scheme)) -> str:
    merchant_name = MOCK_MERCHANT_TOKENS.get(token)
    if not merchant_name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return merchant_name

import os
import jwt
from datetime import datetime, timedelta, timezone

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-demo-key-123")
ALGORITHM = "HS256"

def generate_customer_token(transaction_id: int) -> str:
    """Generates a short-lived token for the customer self-schedule link."""
    payload = {
        "txn_id": transaction_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=3) # Link valid for 3 days
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)

def verify_customer_token(token: str) -> int:
    """Verifies the customer token and returns the transaction ID."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload.get("txn_id")
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. The link is no longer valid.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
        )
