"""
WhatsApp Phone Number Pairing Router.

Provides API endpoints for single-phone and headless linking workflows:
- POST /api/whatsapp/pair-phone: Initiates pairing code generation for given phone number
- GET  /api/whatsapp/pair-status: Checks status of code generation or phone authentication
- POST /api/whatsapp/pair-cancel: Cancels current pairing session
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

from backend.whatsapp_pairing import whatsapp_pairing
from logger import get_logger

logger = get_logger("PairingRouter")
router = APIRouter(prefix="/api/whatsapp", tags=["WhatsApp Pairing"])


class PairPhoneRequest(BaseModel):
    phone_number: str = Field(..., description="Phone number with country code, e.g. +14155552671")


@router.post("/pair-phone")
def request_phone_pairing(payload: PairPhoneRequest) -> Dict[str, Any]:
    """
    Submits phone number to WhatsApp Web and retrieves an 8-character pairing code.
    Designed for single-phone users who cannot scan a QR code from the same device.
    """
    res = whatsapp_pairing.request_phone_pairing(payload.phone_number)
    if not res.get("success") and res.get("status") in ("invalid_phone", "browser_error", "code_timeout", "input_not_found"):
        raise HTTPException(status_code=400, detail=res)
    return res


@router.get("/pair-status")
def get_pairing_status() -> Dict[str, Any]:
    """
    Polls the current status of the pairing code request or authentication confirmation.
    """
    return whatsapp_pairing.get_pairing_status()


@router.post("/pair-cancel")
def cancel_pairing() -> Dict[str, Any]:
    """
    Cancels the active pairing session.
    """
    return whatsapp_pairing.cancel_pairing()
