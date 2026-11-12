"""Firestore campaign lifecycle and funding-summary helpers."""

from time import time


CAMPAIGN_STATUSES = {
    "DRAFT",
    "PENDING_APPROVAL",
    "APPROVED",
    "REJECTED",
    "COMPLETED",
}


class CampaignNotFoundError(LookupError):
    pass


class InvalidCampaignTransition(ValueError):
    pass


class UnverifiedIncidentError(ValueError):
    pass


class DonationOrderNotFoundError(LookupError):
    pass


class DonationOrderStateError(ValueError):
    pass


def campaign_summary(data, campaign_id):
    campaign = dict(data or {})
    target = float(campaign.get("target_funding_amount", campaign.get("goal_amount", 0)) or 0)
    raised = float(campaign.get("current_funding_amount", 0) or 0)
    remaining = max(target - raised, 0.0)
    progress = min(raised / target * 100, 100.0) if target > 0 else 0.0
    campaign.update(
        {
            "id": campaign_id,
            "campaign_id": campaign.get("campaign_id", campaign_id),
            "status": str(campaign.get("status", "DRAFT")).upper(),
            "target_funding_amount": target,
            "current_funding_amount": raised,
            "remaining_amount": remaining,
            "funding_progress_percentage": round(progress, 2),
        }
    )
    return campaign


def list_campaign_records(db, *, approved_only=False):
    campaigns = []
    for document in db.collection("campaigns").stream():
        data = document.to_dict() or {}
        status = str(data.get("status", "DRAFT")).upper()
        if approved_only and status not in {"APPROVED", "COMPLETED"}:
            continue
        campaigns.append(campaign_summary(data, document.id))
    campaigns.sort(
        key=lambda item: item.get("created_timestamp", item.get("created_at", 0)),
        reverse=True,
    )
    return campaigns


def create_campaign_record(db, values, admin):
    incident_id = values["incident_id"]
    incident = db.collection("alerts").document(incident_id).get()
    if not incident.exists or (incident.to_dict() or {}).get("status") != "confirmed":
        raise UnverifiedIncidentError(
            "Campaigns can only be created for human-verified incidents."
        )

    created_timestamp = time()
    payload = {
        "incident_id": incident_id,
        "title": values["title"].strip(),
        "description": values["description"].strip(),
        "emergency_category": values["emergency_category"].strip(),
        "location": values["location"].strip(),
        "target_funding_amount": float(values["target_funding_amount"]),
        "current_funding_amount": 0.0,
        "currency": values.get("currency", "USD"),
        "status": "DRAFT",
        "created_timestamp": created_timestamp,
        "created_at": created_timestamp,
        "created_by": admin.get("email") or admin.get("uid"),
        "approved_by": None,
        "approved_at": None,
    }
    _, reference = db.collection("campaigns").add(payload)
    reference.update({"campaign_id": reference.id})
    return campaign_summary(reference.get().to_dict(), reference.id)


def _campaign_reference(db, campaign_id):
    reference = db.collection("campaigns").document(campaign_id)
    if not reference.get().exists:
        raise CampaignNotFoundError(campaign_id)
    return reference


def submit_campaign_record(db, campaign_id):
    reference = _campaign_reference(db, campaign_id)
    campaign = reference.get().to_dict() or {}
    if str(campaign.get("status", "")).upper() != "DRAFT":
        raise InvalidCampaignTransition("Only DRAFT campaigns can be submitted.")
    reference.update({"status": "PENDING_APPROVAL"})
    return campaign_summary(reference.get().to_dict(), campaign_id)


def review_campaign_record(db, campaign_id, decision, admin):
    decision = decision.upper()
    if decision not in {"APPROVED", "REJECTED"}:
        raise InvalidCampaignTransition("Review decision must be APPROVED or REJECTED.")
    reference = _campaign_reference(db, campaign_id)
    campaign = reference.get().to_dict() or {}
    if str(campaign.get("status", "")).upper() != "PENDING_APPROVAL":
        raise InvalidCampaignTransition(
            "Only PENDING_APPROVAL campaigns can be approved or rejected."
        )
    reference.update(
        {
            "status": decision,
            "approved_by": admin.get("email") or admin.get("uid"),
            "approved_at": time(),
        }
    )
    return campaign_summary(reference.get().to_dict(), campaign_id)


def refresh_campaign_funding(db, campaign_id):
    """Recalculate raised funds from recorded completed transactions."""
    reference = _campaign_reference(db, campaign_id)
    campaign = reference.get().to_dict() or {}
    raised = sum(
        float((document.to_dict() or {}).get("amount", 0) or 0)
        for document in db.collection("donation_transactions").stream()
        if (document.to_dict() or {}).get("campaign_id") == campaign_id
        and (document.to_dict() or {}).get("status") == "completed"
    )
    target = float(
        campaign.get("target_funding_amount", campaign.get("goal_amount", 0)) or 0
    )
    updates = {"current_funding_amount": round(raised, 2)}
    if target > 0 and raised >= target and str(campaign.get("status", "")).upper() == "APPROVED":
        updates["status"] = "COMPLETED"
    reference.update(updates)
    return campaign_summary(reference.get().to_dict(), campaign_id)


def create_donation_order_records(
    db,
    *,
    order_id,
    campaign_id,
    amount,
    currency,
    donor_uid,
    paypal_request_id,
):
    created_at = time()
    order_data = {
        "order_id": order_id,
        "campaign_id": campaign_id,
        "amount": amount,
        "currency": currency,
        "donor_uid": donor_uid,
        "created_at": created_at,
        "expires_at": created_at + 3 * 60 * 60,
        "status": "PENDING",
        "paypal_request_id": paypal_request_id,
    }
    db.collection("donation_orders").document(order_id).set(order_data)
    db.collection("donation_transactions").document(order_id).set(
        {
            **order_data,
            "transaction_id": None,
            "payment_status": "PENDING",
        }
    )
    return order_data


def find_donation_order(db, order_id):
    order = db.collection("donation_orders").document(order_id).get()
    if order.exists:
        return order
    for candidate in db.collection("donation_orders").stream():
        if (candidate.to_dict() or {}).get("order_id") == order_id:
            return candidate
    raise DonationOrderNotFoundError(order_id)


def active_order_reservations(db, campaign_id, *, now=None):
    now = time() if now is None else now
    reserved = 0.0
    for document in db.collection("donation_orders").stream():
        order = document.to_dict() or {}
        if (
            order.get("campaign_id") == campaign_id
            and order.get("status") == "PENDING"
            and float(order.get("expires_at", 0) or 0) > now
        ):
            reserved += float(order.get("amount", 0) or 0)
    return reserved


def cancel_donation_order(db, order_id):
    order_ref = db.collection("donation_orders").document(order_id)
    order = order_ref.get()
    if not order.exists:
        raise DonationOrderNotFoundError(order_id)
    data = order.to_dict() or {}
    if data.get("status") == "COMPLETED":
        raise DonationOrderStateError("Completed donations cannot be cancelled.")
    if data.get("status") != "PENDING":
        transaction = db.collection("donation_transactions").document(order_id).get()
        return transaction.to_dict() if transaction.exists else data
    cancelled_at = time()
    order_ref.update({"status": "CANCELLED", "cancelled_at": cancelled_at})
    db.collection("donation_transactions").document(order_id).update(
        {"payment_status": "CANCELLED", "cancelled_at": cancelled_at}
    )
    return db.collection("donation_transactions").document(order_id).get().to_dict()


def update_donation_order_status(db, order_id, status):
    if status not in {"PENDING", "FAILED", "CANCELLED"}:
        raise DonationOrderStateError("Invalid non-completed payment status.")
    order_ref = db.collection("donation_orders").document(order_id)
    order = order_ref.get()
    if not order.exists:
        raise DonationOrderNotFoundError(order_id)
    if (order.to_dict() or {}).get("status") == "COMPLETED":
        return db.collection("donation_transactions").document(order_id).get().to_dict()
    updated_at = time()
    order_ref.update({"status": status, "updated_at": updated_at})
    transaction_ref = db.collection("donation_transactions").document(order_id)
    transaction_ref.update({"payment_status": status, "updated_at": updated_at})
    return transaction_ref.get().to_dict()


def finalize_donation_capture(db, order_id, capture):
    """Atomically persist one completed capture and update its campaign funding."""
    order_ref = db.collection("donation_orders").document(order_id)
    payment_ref = db.collection("donation_transactions").document(order_id)
    order_snapshot = order_ref.get()
    if not order_snapshot.exists:
        raise DonationOrderNotFoundError(order_id)
    order_data = order_snapshot.to_dict() or {}

    transaction_factory = getattr(db, "transaction", None)
    if transaction_factory is not None:
        transaction = transaction_factory()
        order_snapshot = order_ref.get(transaction=transaction)
        payment_snapshot = payment_ref.get(transaction=transaction)
        order_data = order_snapshot.to_dict() or {}
        payment_data = payment_snapshot.to_dict() if payment_snapshot.exists else {}
        if payment_data.get("payment_status") == "COMPLETED":
            return payment_data
        if order_data.get("status") != "PENDING":
            raise DonationOrderStateError("Donation order is not pending capture.")
        campaign_ref = db.collection("campaigns").document(order_data["campaign_id"])
        campaign_snapshot = campaign_ref.get(transaction=transaction)
        if not campaign_snapshot.exists:
            raise CampaignNotFoundError(order_data["campaign_id"])
        campaign = campaign_snapshot.to_dict() or {}
        if campaign.get("status") not in {"APPROVED", "COMPLETED"}:
            raise DonationOrderStateError("Campaign is no longer accepting donations.")
        raised = float(campaign.get("current_funding_amount", 0) or 0)
        target = float(campaign.get("target_funding_amount", 0) or 0)
        new_raised = round(raised + float(capture["amount"]), 2)
        completed_at = time()
        transaction_data = {
            **order_data,
            "transaction_id": capture["transaction_id"],
            "payment_status": "COMPLETED",
            "status": "completed",
            "amount": capture["amount"],
            "currency": capture["currency"],
            "captured_at": completed_at,
            "created_at": completed_at,
        }
        transaction.set(payment_ref, transaction_data)
        transaction.update(
            order_ref,
            {"status": "COMPLETED", "transaction_id": capture["transaction_id"], "captured_at": completed_at},
        )
        campaign_updates = {"current_funding_amount": new_raised}
        if target > 0 and new_raised >= target:
            campaign_updates["status"] = "COMPLETED"
        transaction.update(campaign_ref, campaign_updates)
        transaction.commit()
        return transaction_data

    payment_snapshot = payment_ref.get()
    payment_data = payment_snapshot.to_dict() if payment_snapshot.exists else {}
    if payment_data.get("payment_status") == "COMPLETED":
        refresh_campaign_funding(db, order_data["campaign_id"])
        return payment_data
    if order_data.get("status") != "PENDING":
        raise DonationOrderStateError("Donation order is not pending capture.")
    campaign_ref = db.collection("campaigns").document(order_data["campaign_id"])
    campaign_snapshot = campaign_ref.get()
    if not campaign_snapshot.exists:
        raise CampaignNotFoundError(order_data["campaign_id"])
    campaign = campaign_snapshot.to_dict() or {}
    if campaign.get("status") not in {"APPROVED", "COMPLETED"}:
        raise DonationOrderStateError("Campaign is no longer accepting donations.")
    new_raised = round(
        float(campaign.get("current_funding_amount", 0) or 0)
        + float(capture["amount"]),
        2,
    )
    target = float(campaign.get("target_funding_amount", 0) or 0)
    completed_at = time()
    transaction_data = {
        **order_data,
        "transaction_id": capture["transaction_id"],
        "payment_status": "COMPLETED",
        "status": "completed",
        "amount": capture["amount"],
        "currency": capture["currency"],
        "captured_at": completed_at,
        "created_at": completed_at,
    }
    payment_ref.set(transaction_data)
    order_ref.update(
        {"status": "COMPLETED", "transaction_id": capture["transaction_id"], "captured_at": completed_at}
    )
    campaign_updates = {"current_funding_amount": new_raised}
    if target > 0 and new_raised >= target:
        campaign_updates["status"] = "COMPLETED"
    campaign_ref.update(campaign_updates)
    return transaction_data
