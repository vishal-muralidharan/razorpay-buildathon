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
