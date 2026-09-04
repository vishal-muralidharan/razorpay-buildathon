from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid

from app import models, razorpay_client
from app.database import get_db

router = APIRouter(prefix="/registration", tags=["registration"])

class RegisterCustomerRequest(BaseModel):
    name: str
    phone: str
    email: str

class RegisterCustomerResponse(BaseModel):
    customer_id: int
    razorpay_customer_id: str

class CreateOrderRequest(BaseModel):
    customer_id: int
    razorpay_customer_id: str

class CreateOrderResponse(BaseModel):
    order_id: str
    amount: float
    currency: str

class VerifyRegistrationRequest(BaseModel):
    customer_id: int
    razorpay_customer_id: str
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str
    amount: float = 1000.0  # Default actual mandate amount (e.g. 1000 INR)

class VerifyRegistrationResponse(BaseModel):
    status: str
    mandate_id: int

@router.post("/customers", response_model=RegisterCustomerResponse)
def register_customer(req: RegisterCustomerRequest, db: Session = Depends(get_db)):
    try:
        rzp_customer = razorpay_client.create_customer(req.name, req.email, req.phone)
        rzp_cust_id = rzp_customer.get("id")
        if not rzp_cust_id:
            raise HTTPException(status_code=500, detail="Failed to get customer ID from Razorpay")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    new_customer = models.Customer(
        name=req.name,
        phone=req.phone,
        preferred_language="en"
    )
    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)

    return RegisterCustomerResponse(
        customer_id=new_customer.id,
        razorpay_customer_id=rzp_cust_id
    )

@router.post("/orders", response_model=CreateOrderResponse)
def create_mandate_order(req: CreateOrderRequest, db: Session = Depends(get_db)):
    receipt = f"rcpt_{uuid.uuid4().hex[:8]}"
    amount = 1.0 # 1 INR for mandate setup
    
    try:
        rzp_order = razorpay_client.create_mandate_order(amount, req.razorpay_customer_id, receipt)
        return CreateOrderResponse(
            order_id=rzp_order["id"],
            amount=amount,
            currency="INR"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/verify", response_model=VerifyRegistrationResponse)
def verify_registration(req: VerifyRegistrationRequest, db: Session = Depends(get_db)):
    is_valid = razorpay_client.verify_signature(
        req.razorpay_order_id, 
        req.razorpay_payment_id, 
        req.razorpay_signature
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    try:
        payment = razorpay_client.fetch_payment(req.razorpay_payment_id)
        token_id = payment.get("token_id")
        if not token_id:
            raise HTTPException(status_code=400, detail="No token_id found in payment")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    new_mandate = models.Mandate(
        customer_id=req.customer_id,
        amount=req.amount,
        frequency="MONTHLY",
        status="ACTIVE",
        merchant_name="Vela SaaS",
        razorpay_customer_id=req.razorpay_customer_id,
        razorpay_token_id=token_id
    )
    db.add(new_mandate)
    db.commit()
    db.refresh(new_mandate)

    return VerifyRegistrationResponse(
        status="success",
        mandate_id=new_mandate.id
    )
