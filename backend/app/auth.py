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

import os
import jwt
from jwt import PyJWKClient
from datetime import datetime, timedelta, timezone

OIDC_ISSUER = os.getenv("OIDC_ISSUER")  # e.g., "https://my-tenant.auth0.com/"
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE")  # e.g., "https://api.vela.com"

jwks_client = None
if OIDC_ISSUER:
    jwks_url = f"{OIDC_ISSUER.rstrip('/')}/.well-known/jwks.json"
    jwks_client = PyJWKClient(jwks_url)

def verify_merchant(token: str = Depends(oauth2_scheme)) -> str:
    # If a real Identity Provider is configured, validate the JWT securely.
    if jwks_client and OIDC_ISSUER and OIDC_AUDIENCE:
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=OIDC_AUDIENCE,
                issuer=OIDC_ISSUER
            )
            # Depending on the IdP setup, the merchant name might be in a custom claim or client_id.
            # We assume a standard 'client_id' or a custom claim for the demo.
            merchant_name = payload.get("merchant_name") or payload.get("client_id")
            if not merchant_name:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="JWT does not contain a valid merchant identity claim.",
                )
            return merchant_name
        except jwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid authentication credentials: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Fallback to local mock tokens for the demo environment if no IdP is configured.
    merchant_name = MOCK_MERCHANT_TOKENS.get(token)
    if not merchant_name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return merchant_name

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
