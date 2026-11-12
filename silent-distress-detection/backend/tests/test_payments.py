import unittest

from resqpay.payments import (
    PaymentConfigurationError,
    PayPalClient,
    PayPalRequestError,
    validate_capture_response,
)


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def raise_for_status(self):
        return None

    def json(self):
        return self.value


class FakeSession:
    def __init__(self, order_response=None, capture_response=None):
        self.order_response = order_response or {
            "id": "ORDER-1",
            "links": [
                {
                    "rel": "approve",
                    "href": "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-1",
                }
            ],
        }
        self.capture_response = capture_response or {}
        self.oauth_calls = []
        self.api_calls = []

    def post(self, url, **kwargs):
        self.oauth_calls.append((url, kwargs))
        return FakeResponse({"access_token": "sandbox-access-token"})

    def request(self, method, url, **kwargs):
        self.api_calls.append((method, url, kwargs))
        if url.endswith("/capture"):
            return FakeResponse(self.capture_response)
        return FakeResponse(self.order_response)


class PayPalClientTests(unittest.TestCase):
    def test_sandbox_configuration_rejects_live_api(self):
        with self.assertRaises(PaymentConfigurationError):
            PayPalClient(
                client_id="sandbox-id",
                client_secret="sandbox-secret",
                base_url="https://api-m.paypal.com",
                session=FakeSession(),
            )

    def test_missing_credentials_fail_clearly(self):
        with self.assertRaises(PaymentConfigurationError):
            PayPalClient(
                client_id="",
                client_secret="",
                base_url="https://api-m.sandbox.paypal.com",
                session=FakeSession(),
            )

    def test_create_order_uses_oauth_and_returns_sandbox_approval(self):
        session = FakeSession()
        paypal = PayPalClient(
            client_id="sandbox-id",
            client_secret="sandbox-secret",
            session=session,
        )

        order, approval_url, request_id = paypal.create_order(
            campaign_id="campaign-1",
            amount="12.50",
            currency="USD",
            return_url="http://localhost:3000/donations",
            cancel_url="http://localhost:3000/donations?cancelled=1",
        )

        oauth_url, oauth_args = session.oauth_calls[0]
        self.assertTrue(oauth_url.endswith("/v1/oauth2/token"))
        self.assertEqual(oauth_args["auth"], ("sandbox-id", "sandbox-secret"))
        self.assertEqual(order["id"], "ORDER-1")
        self.assertIn("sandbox.paypal.com", approval_url)
        self.assertEqual(session.api_calls[0][2]["headers"]["Authorization"], "Bearer sandbox-access-token")
        self.assertEqual(session.api_calls[0][2]["headers"]["PayPal-Request-Id"], request_id)
        self.assertEqual(
            session.api_calls[0][2]["json"]["purchase_units"][0]["amount"]["value"],
            "12.50",
        )

    def test_non_sandbox_approval_url_is_rejected(self):
        session = FakeSession(
            order_response={
                "id": "ORDER-1",
                "links": [{"rel": "approve", "href": "https://paypal.example/checkout"}],
            }
        )
        paypal = PayPalClient(
            client_id="sandbox-id",
            client_secret="sandbox-secret",
            session=session,
        )

        with self.assertRaises(PayPalRequestError):
            paypal.create_order(
                campaign_id="campaign-1",
                amount="12.50",
                currency="USD",
                return_url="http://localhost:3000/donations",
                cancel_url="http://localhost:3000/donations?cancelled=1",
            )

    def test_capture_is_validated_against_stored_order(self):
        result = {
            "id": "ORDER-1",
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "reference_id": "campaign-1",
                    "custom_id": "campaign-1",
                    "payments": {
                        "captures": [
                            {
                                "id": "CAPTURE-1",
                                "status": "COMPLETED",
                                "amount": {"currency_code": "USD", "value": "12.50"},
                            }
                        ]
                    },
                }
            ],
        }
        capture = validate_capture_response(
            result,
            order_id="ORDER-1",
            campaign_id="campaign-1",
            amount="12.50",
            currency="USD",
        )
        self.assertEqual(capture["transaction_id"], "CAPTURE-1")
        self.assertEqual(capture["amount"], "12.50")

        with self.assertRaises(ValueError):
            validate_capture_response(
                result,
                order_id="ORDER-1",
                campaign_id="another-campaign",
                amount="12.50",
                currency="USD",
            )
        pending = dict(result, status="PAYER_ACTION_REQUIRED")
        with self.assertRaisesRegex(ValueError, "not confirmed"):
            validate_capture_response(
                pending,
                order_id="ORDER-1",
                campaign_id="campaign-1",
                amount="12.50",
                currency="USD",
            )
        with self.assertRaises(ValueError):
            validate_capture_response(
                result,
                order_id="ORDER-1",
                campaign_id="campaign-1",
                amount="20.00",
                currency="USD",
            )


if __name__ == "__main__":
    unittest.main()
