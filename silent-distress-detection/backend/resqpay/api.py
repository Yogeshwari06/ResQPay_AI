import os
import math
from decimal import Decimal
from time import time
from datetime import datetime
from typing import Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from google.api_core.exceptions import GoogleAPICallError
from pydantic import BaseModel, Field, validator

from ai.incident_intelligence import analyze_incident, assess_incident
from config.firebase_config import db
from resqpay.campaign_service import (
    CampaignNotFoundError,
    DonationOrderNotFoundError,
    DonationOrderStateError,
    InvalidCampaignTransition,
    UnverifiedIncidentError,
    active_order_reservations,
    campaign_summary,
    cancel_donation_order,
    create_campaign_record,
    create_donation_order_records,
    finalize_donation_capture,
    find_donation_order,
    list_campaign_records,
    review_campaign_record,
    submit_campaign_record,
    update_donation_order_status,
)
from resqpay.payments import (
    PaymentConfigurationError,
    PayPalClient,
    PayPalRequestError,
    validate_capture_response,
)
from utils.security import verify_firebase_token

router = APIRouter(prefix="/api", tags=["ResQPay AI"])


class IncidentVerification(BaseModel):
    status: Literal["confirmed", "dismissed", "resolved"]
    note: Optional[str] = None


class IncidentAssessmentInput(BaseModel):
    face_result: Optional[dict] = None
    posture_result: Optional[dict] = None
    audio_result: Optional[dict] = None
    fusion_result: Optional[dict] = None
    timestamp: Optional[Union[datetime, float, str]] = None


class CampaignCreate(BaseModel):
    incident_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=10, max_length=2000)
    emergency_category: str = Field(min_length=3, max_length=80)
    location: str = Field(min_length=2, max_length=200)
    target_funding_amount: float = Field(gt=0, le=10000000)
    currency: Literal["USD"] = "USD"

    @validator("target_funding_amount")
    def target_must_be_finite(cls, value):
        if not math.isfinite(value):
            raise ValueError("Target funding amount must be a finite number.")
        return value


class DonationOrderCreate(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=10000000)

    @validator("amount")
    def amount_must_be_finite(cls, value):
        if not math.isfinite(value):
            raise ValueError("Donation amount must be a finite number.")
        return value


class DonationCapture(BaseModel):
    order_id: str = Field(min_length=1, max_length=200)


class DonationCancellation(BaseModel):
    order_id: str = Field(min_length=1, max_length=200)


def _document_data(document):
    data = document.to_dict() or {}
    data["id"] = document.id
    return data


def _find_document(collection_name, document_id):
    document = db.collection(collection_name).document(document_id).get()
    if not document.exists:
        raise HTTPException(status_code=404, detail="Record not found.")
    return document


def _require_admin(user=Depends(verify_firebase_token)):
    admin_emails = {
        address.strip().lower()
        for address in os.getenv("RESQPAY_ADMIN_EMAILS", "").split(",")
        if address.strip()
    }
    email = str(user.get("email", "")).lower()
    if not user.get("admin") and email not in admin_emails:
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user


def _is_admin(user):
    admin_emails = {
        address.strip().lower()
        for address in os.getenv("RESQPAY_ADMIN_EMAILS", "").split(",")
        if address.strip()
    }
    return bool(user.get("admin")) or str(user.get("email", "")).lower() in admin_emails


@router.post("/incidents/assess")
def assess_incident_signals(
    signals: IncidentAssessmentInput,
    user=Depends(verify_firebase_token),
):
    """Assess submitted detector outputs without persisting or triggering a response."""
    try:
        return assess_incident(**signals.dict())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/incidents")
def list_incidents(user=Depends(verify_firebase_token)):
    incidents = []
    for document in db.collection("alerts").stream():
        incident = _document_data(document)
        incident["intelligence"] = analyze_incident(incident)
        incidents.append(incident)
    incidents.sort(key=lambda item: item.get("timestamp", 0), reverse=True)
    return incidents


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, user=Depends(verify_firebase_token)):
    incident = _document_data(_find_document("alerts", incident_id))
    incident["intelligence"] = analyze_incident(incident)
    return incident


@router.patch("/incidents/{incident_id}/verification")
def verify_incident(
    incident_id: str,
    verification: IncidentVerification,
    user=Depends(verify_firebase_token),
):
    reference = db.collection("alerts").document(incident_id)
    document = reference.get()
    if not document.exists:
        raise HTTPException(status_code=404, detail="Incident not found.")

    verified_at = time()
    reference.update(
        {
            "status": verification.status,
            "reviewer": user.get("email") or user.get("uid"),
            "verification_note": verification.note,
            "verified_at": verified_at,
        }
    )
    incident = _document_data(reference.get())
    incident["intelligence"] = analyze_incident(incident)
    return incident


@router.get("/campaigns")
def list_campaigns():
    return list_campaign_records(db, approved_only=True)


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: str):
    document = _find_document("campaigns", campaign_id)
    campaign = campaign_summary(document.to_dict(), document.id)
    if campaign.get("status") not in {"APPROVED", "COMPLETED"}:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return campaign


@router.get("/admin/campaigns")
def list_campaigns_for_admin(user=Depends(_require_admin)):
    return list_campaign_records(db)


@router.post("/campaigns", status_code=201)
def create_campaign(
    campaign: CampaignCreate,
    user=Depends(_require_admin),
):
    try:
        return create_campaign_record(db, campaign.dict(), user)
    except UnverifiedIncidentError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/campaigns/{campaign_id}/submit")
def submit_campaign(
    campaign_id: str,
    user=Depends(_require_admin),
):
    try:
        return submit_campaign_record(db, campaign_id)
    except CampaignNotFoundError as error:
        raise HTTPException(status_code=404, detail="Campaign not found.") from error
    except InvalidCampaignTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.patch("/campaigns/{campaign_id}/approval")
def approve_campaign(
    campaign_id: str,
    approved: bool,
    user=Depends(_require_admin),
):
    try:
        return review_campaign_record(
            db, campaign_id, "APPROVED" if approved else "REJECTED", user
        )
    except CampaignNotFoundError as error:
        raise HTTPException(status_code=404, detail="Campaign not found.") from error
    except InvalidCampaignTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/donations/create-order")
def create_donation_order(
    donation: DonationOrderCreate,
    user=Depends(verify_firebase_token),
):
    campaign = campaign_summary(
        _find_document("campaigns", donation.campaign_id).to_dict(),
        donation.campaign_id,
    )
    campaign_status = str(campaign.get("status", "")).upper()
    if campaign_status != "APPROVED":
        raise HTTPException(status_code=409, detail="Campaign is not approved for donations.")
    amount = Decimal(str(donation.amount)).quantize(Decimal("0.01"))
    if not amount.is_finite() or amount <= 0:
        raise HTTPException(status_code=422, detail="Donation amount must be positive.")
    available_amount = round(
        campaign["remaining_amount"]
        - active_order_reservations(db, donation.campaign_id),
        2,
    )
    if float(amount) > available_amount:
        raise HTTPException(
            status_code=409,
            detail=f"Donation exceeds the unreserved campaign balance of {max(available_amount, 0):.2f} USD.",
        )

    frontend_url = os.getenv("RESQPAY_FRONTEND_URL", "http://localhost:3000").rstrip("/")
    try:
        paypal = PayPalClient()
        paypal_order, approval_url, paypal_request_id = paypal.create_order(
            campaign_id=donation.campaign_id,
            amount=f"{amount:.2f}",
            currency=campaign.get("currency", "USD"),
            return_url=f"{frontend_url}/donations",
            cancel_url=f"{frontend_url}/donations?cancelled=1",
        )
    except PaymentConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except PayPalRequestError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    order_id = paypal_order["id"]
    try:
        create_donation_order_records(
            db,
            order_id=order_id,
            campaign_id=donation.campaign_id,
            amount=f"{amount:.2f}",
            currency=campaign.get("currency", "USD"),
            donor_uid=user.get("uid"),
            paypal_request_id=paypal_request_id,
        )
    except (GoogleAPICallError, OSError, ValueError, RuntimeError) as error:
        raise HTTPException(
            status_code=503,
            detail="PayPal created the order, but it could not be recorded. Contact support before retrying.",
        ) from error
    return {
        "order_id": order_id,
        "approval_url": approval_url,
        "status": "PENDING",
    }


@router.post("/donations/capture")
def capture_donation(
    donation: DonationCapture,
    user=Depends(verify_firebase_token),
):
    try:
        order_record = find_donation_order(db, donation.order_id)
    except DonationOrderNotFoundError as error:
        raise HTTPException(status_code=404, detail="Donation order not found.") from error
    order_data = order_record.to_dict() or {}
    if order_data.get("donor_uid") != user.get("uid") and not _is_admin(user):
        raise HTTPException(status_code=403, detail="This donation order belongs to another user.")

    payment_snapshot = db.collection("donation_transactions").document(donation.order_id).get()
    if payment_snapshot.exists and (payment_snapshot.to_dict() or {}).get("payment_status") == "COMPLETED":
        return _document_data(payment_snapshot)
    if order_data.get("status") == "CANCELLED":
        raise HTTPException(status_code=409, detail="Donation was cancelled in PayPal checkout.")
    if order_data.get("status") != "PENDING":
        raise HTTPException(status_code=409, detail=f"Donation order is {order_data.get('status', 'unavailable').lower()}.")

    try:
        result = PayPalClient().capture_order(donation.order_id)
    except PaymentConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except PayPalRequestError as error:
        # A network or provider error is ambiguous; leave the record PENDING so
        # the same PayPal order can safely be retried with its idempotency key.
        raise HTTPException(status_code=502, detail=str(error)) from error

    if result.get("status") in {"VOIDED", "DENIED"}:
        status = "CANCELLED" if result.get("status") == "VOIDED" else "FAILED"
        update_donation_order_status(db, donation.order_id, status)
        raise HTTPException(status_code=409, detail=f"PayPal payment is {status.lower()}.")
    if result.get("status") != "COMPLETED":
        update_donation_order_status(db, donation.order_id, "PENDING")
        raise HTTPException(
            status_code=409,
            detail=f"PayPal payment is not complete (status: {result.get('status', 'unknown')}).",
        )

    try:
        capture = validate_capture_response(
            result,
            order_id=donation.order_id,
            campaign_id=order_data["campaign_id"],
            amount=order_data["amount"],
            currency=order_data["currency"],
        )
        finalized = finalize_donation_capture(db, donation.order_id, capture)
        return {"id": donation.order_id, **finalized}
    except GoogleAPICallError as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "PayPal confirmed payment, but saving the transaction failed. "
                "Retry this order safely; duplicate funding is prevented."
            ),
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (CampaignNotFoundError, DonationOrderNotFoundError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except DonationOrderStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/donations/cancel")
def cancel_donation(
    donation: DonationCancellation,
    user=Depends(verify_firebase_token),
):
    try:
        order = find_donation_order(db, donation.order_id)
        order_data = order.to_dict() or {}
        if order_data.get("donor_uid") != user.get("uid") and not _is_admin(user):
            raise HTTPException(
                status_code=403,
                detail="This donation order belongs to another user.",
            )
        return cancel_donation_order(db, donation.order_id)
    except DonationOrderNotFoundError as error:
        raise HTTPException(status_code=404, detail="Donation order not found.") from error
    except DonationOrderStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/transactions")
def list_transactions(user=Depends(verify_firebase_token)):
    is_admin = _is_admin(user)
    transactions = []
    for document in db.collection("donation_transactions").stream():
        transaction = document.to_dict() or {}
        if is_admin or transaction.get("donor_uid") == user.get("uid"):
            transaction["id"] = document.id
            transactions.append(transaction)
    transactions.sort(
        key=lambda item: item.get("captured_at", item.get("created_at", 0)),
        reverse=True,
    )
    return transactions
