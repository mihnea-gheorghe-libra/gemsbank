from fastapi import FastAPI, APIRouter, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional, Literal
from bson import ObjectId
import os

from .email import generate_otp, send_otp_email
from datetime import timedelta

app = FastAPI(title="gems-bank API")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017/gems?replicaSet=rs0")
client = AsyncIOMotorClient(MONGO_URI)
db = client["gems"]

def kyc_cases_collection():
    return db["kycCases"]

def users_collection():
    return db["users"]

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/db-check")
async def db_check():
    result = await db.command("ping")
    return {"mongo_ok": result.get("ok") == 1.0}

class KycCase(BaseModel):
    userId: Optional[str] = None
    docRef: Optional[str] = None
    extracted: dict = Field(default_factory=dict)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    otpVerified: bool = False
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    phone: str
    passwordHash: str
    pinHash: str
    kycCaseId: str

class User(UserCreate):
    prefs: dict = Field(default_factory=lambda: {"lang": "ro", "theme": "light", "tts": False})
    status: Literal["active", "suspended"] = "active"
    createdAt: datetime = Field(default_factory=datetime.utcnow)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

@router.post("/start")
async def start_onboarding(phone: str, email: str):
    kyc = KycCase(phone=phone, email=email)
    result = await kyc_cases_collection().insert_one(kyc.model_dump())

    otp_code = generate_otp()
    send_otp_email(email, otp_code)

    await kyc_cases_collection().update_one(
        {"_id": result.inserted_id},
        {"$set": {
            "otpCode": otp_code,
            "otpExpiresAt": datetime.utcnow() + timedelta(minutes=5)
        }}
    )

    return {"kycCaseId": str(result.inserted_id)}

@router.post("/{kyc_case_id}/otp-verify")
async def verify_otp(kyc_case_id: str, code: str):
    kyc = await kyc_cases_collection().find_one({"_id": ObjectId(kyc_case_id)})

    if not kyc or kyc.get("otpCode") != code:
        raise HTTPException(400, "Cod incorect")
    if datetime.utcnow() > kyc["otpExpiresAt"]:
        raise HTTPException(400, "Cod expirat")

    await kyc_cases_collection().update_one(
        {"_id": ObjectId(kyc_case_id)},
        {
            "$set": {"otpVerified": True, "updatedAt": datetime.utcnow()},
            "$unset": {"otpCode": ""}
        }
    )
    return {"status": "otp_verified"}

@router.post("/{kyc_case_id}/document")
async def upload_document(kyc_case_id: str, doc_ref: str, extracted: dict):
    await kyc_cases_collection().update_one(
        {"_id": ObjectId(kyc_case_id)},
        {"": {"docRef": doc_ref, "extracted": extracted, "updatedAt": datetime.utcnow()}}
    )
    return {"status": "document_uploaded"}

@router.post("/{kyc_case_id}/complete")
async def complete_onboarding(kyc_case_id: str, credentials: UserCreate):
    kyc = await kyc_cases_collection().find_one({"_id": ObjectId(kyc_case_id)})
    if not kyc or not kyc.get("otpVerified") or not kyc.get("docRef"):
        raise HTTPException(400, "KYC not complete")

    user_doc = credentials.model_dump()
    user_doc["kycCaseId"] = kyc_case_id
    user_doc["prefs"] = {"lang": "ro", "theme": "light", "tts": False}
    user_doc["status"] = "active"
    user_doc["createdAt"] = datetime.utcnow()
    result = await users_collection().insert_one(user_doc)

    await kyc_cases_collection().update_one(
        {"_id": ObjectId(kyc_case_id)},
        {"": {"userId": str(result.inserted_id)}}
    )
    return {"userId": str(result.inserted_id)}

app.include_router(router)
