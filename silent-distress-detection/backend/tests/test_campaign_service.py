import unittest

from resqpay.campaign_service import (
    DonationOrderStateError,
    InvalidCampaignTransition,
    UnverifiedIncidentError,
    active_order_reservations,
    cancel_donation_order,
    create_donation_order_records,
    create_campaign_record,
    finalize_donation_capture,
    list_campaign_records,
    refresh_campaign_funding,
    review_campaign_record,
    submit_campaign_record,
)


class Snapshot:
    def __init__(self, doc_id, data=None):
        self.id = doc_id
        self.exists = data is not None
        self.data = dict(data or {})

    def to_dict(self):
        return dict(self.data)


class DocumentReference:
    def __init__(self, collection, doc_id):
        self.collection = collection
        self.id = doc_id

    def get(self):
        return self.collection.documents.get(
            self.id, Snapshot(self.id)
        )

    def update(self, values):
        if self.id not in self.collection.documents:
            raise KeyError(self.id)
        self.collection.documents[self.id].data.update(values)

    def set(self, values):
        self.collection.documents[self.id] = Snapshot(self.id, values)


class Collection:
    def __init__(self):
        self.documents = {}

    def document(self, doc_id):
        return DocumentReference(self, doc_id)

    def add(self, data):
        doc_id = f"doc-{len(self.documents) + 1}"
        self.documents[doc_id] = Snapshot(doc_id, data)
        return None, DocumentReference(self, doc_id)

    def stream(self):
        return list(self.documents.values())


class MemoryFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = Collection()
        return self.collections[name]


class CampaignServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = MemoryFirestore()
        self.db.collection("alerts").documents["incident-1"] = Snapshot(
            "incident-1", {"status": "confirmed", "reviewer": "staff@example.test"}
        )
        self.payload = {
            "incident_id": "incident-1",
            "title": "Community flood response",
            "description": "Provide temporary supplies to affected residents.",
            "emergency_category": "Flood recovery",
            "location": "North district",
            "target_funding_amount": 12000,
            "currency": "USD",
        }
        self.admin = {"uid": "admin-1", "email": "admin@example.test"}

    def test_create_campaign_for_verified_incident(self):
        campaign = create_campaign_record(self.db, self.payload, self.admin)

        self.assertEqual(campaign["status"], "DRAFT")
        self.assertEqual(campaign["campaign_id"], "doc-1")
        self.assertEqual(campaign["target_funding_amount"], 12000)
        self.assertEqual(campaign["campaign_id"], self.db.collection("campaigns").stream()[0].to_dict()["campaign_id"])
        self.assertEqual(campaign["current_funding_amount"], 0)
        self.assertEqual(campaign["remaining_amount"], 12000)
        self.assertEqual(campaign["funding_progress_percentage"], 0)
        self.assertTrue(campaign["created_timestamp"])

    def test_unverified_incident_is_rejected(self):
        self.db.collection("alerts").documents["incident-1"].data["status"] = "pending"

        with self.assertRaises(UnverifiedIncidentError):
            create_campaign_record(self.db, self.payload, self.admin)

    def test_approval_workflow_and_campaign_listing(self):
        draft = create_campaign_record(self.db, self.payload, self.admin)
        pending = submit_campaign_record(self.db, draft["id"])
        approved = review_campaign_record(self.db, draft["id"], "APPROVED", self.admin)

        self.assertEqual(pending["status"], "PENDING_APPROVAL")
        self.assertEqual(approved["status"], "APPROVED")
        self.assertEqual([item["id"] for item in list_campaign_records(self.db, approved_only=True)], [draft["id"]])
        self.assertEqual(list_campaign_records(self.db)[0]["approved_by"], "admin@example.test")

    def test_rejection_hides_campaign_from_public_listing(self):
        draft = create_campaign_record(self.db, self.payload, self.admin)
        submit_campaign_record(self.db, draft["id"])
        rejected = review_campaign_record(self.db, draft["id"], "REJECTED", self.admin)

        self.assertEqual(rejected["status"], "REJECTED")
        self.assertEqual(list_campaign_records(self.db, approved_only=True), [])

    def test_invalid_campaign_lifecycle_transition(self):
        draft = create_campaign_record(self.db, self.payload, self.admin)

        with self.assertRaises(InvalidCampaignTransition):
            review_campaign_record(self.db, draft["id"], "APPROVED", self.admin)

    def test_completed_donation_updates_funding_and_completes_campaign(self):
        draft = create_campaign_record(self.db, self.payload, self.admin)
        submit_campaign_record(self.db, draft["id"])
        review_campaign_record(self.db, draft["id"], "APPROVED", self.admin)
        self.db.collection("donation_transactions").add(
            {
                "campaign_id": draft["id"],
                "amount": "12000.00",
                "status": "completed",
            }
        )

        updated = refresh_campaign_funding(self.db, draft["id"])

        self.assertEqual(updated["status"], "COMPLETED")
        self.assertEqual(updated["current_funding_amount"], 12000)
        self.assertEqual(updated["remaining_amount"], 0)
        self.assertEqual(updated["funding_progress_percentage"], 100)

    def test_completed_capture_updates_funding_once(self):
        draft = create_campaign_record(self.db, self.payload, self.admin)
        submit_campaign_record(self.db, draft["id"])
        review_campaign_record(self.db, draft["id"], "APPROVED", self.admin)
        create_donation_order_records(
            self.db,
            order_id="ORDER-1",
            campaign_id=draft["id"],
            amount="25.00",
            currency="USD",
            donor_uid="donor-1",
            paypal_request_id="request-1",
        )
        capture = {
            "transaction_id": "CAPTURE-1",
            "amount": "25.00",
            "currency": "USD",
        }

        first = finalize_donation_capture(self.db, "ORDER-1", capture)
        repeated = finalize_donation_capture(self.db, "ORDER-1", capture)

        self.assertEqual(first["payment_status"], "COMPLETED")
        self.assertEqual(repeated["transaction_id"], "CAPTURE-1")
        campaign = self.db.collection("campaigns").document(draft["id"]).get().to_dict()
        self.assertEqual(campaign["current_funding_amount"], 25)
        self.assertEqual(len(self.db.collection("donation_transactions").stream()), 1)

    def test_cancelled_order_releases_reservation_and_cannot_capture(self):
        draft = create_campaign_record(self.db, self.payload, self.admin)
        submit_campaign_record(self.db, draft["id"])
        review_campaign_record(self.db, draft["id"], "APPROVED", self.admin)
        create_donation_order_records(
            self.db,
            order_id="ORDER-2",
            campaign_id=draft["id"],
            amount="25.00",
            currency="USD",
            donor_uid="donor-1",
            paypal_request_id="request-2",
        )

        cancelled = cancel_donation_order(self.db, "ORDER-2")

        self.assertEqual(cancelled["payment_status"], "CANCELLED")
        with self.assertRaises(DonationOrderStateError):
            finalize_donation_capture(
                self.db,
                "ORDER-2",
                {"transaction_id": "CAPTURE-2", "amount": "25.00", "currency": "USD"},
            )

    def test_active_pending_orders_reserve_funding_until_expiry(self):
        create_donation_order_records(
            self.db,
            order_id="ORDER-3",
            campaign_id="campaign-1",
            amount="30.00",
            currency="USD",
            donor_uid="donor-1",
            paypal_request_id="request-3",
        )
        orders = self.db.collection("donation_orders")
        orders.documents["ORDER-3"].data["expires_at"] = 200

        self.assertEqual(active_order_reservations(self.db, "campaign-1", now=100), 30)
        self.assertEqual(active_order_reservations(self.db, "campaign-1", now=201), 0)


if __name__ == "__main__":
    unittest.main()
