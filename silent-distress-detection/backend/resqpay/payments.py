"""PayPal Orders API client for Sandbox donation checkout."""

import os
import math
from urllib.parse import quote, urlparse
from uuid import uuid4

import requests


class PaymentConfigurationError(RuntimeError):
    pass


class PayPalRequestError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class PayPalClient:
    def __init__(self, client_id=None, client_secret=None, base_url=None, session=None):
        self.client_id = client_id or os.getenv("PAYPAL_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("PAYPAL_CLIENT_SECRET")
        self.base_url = (
            base_url or os.getenv(
                "PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com"
            )
        ).rstrip("/")
        self.session = session or requests
        self._validate_configuration()

    def _validate_configuration(self):
        if not self.client_id or not self.client_secret:
            raise PaymentConfigurationError(
                "PayPal Sandbox credentials are not configured on the backend."
            )
        parsed = urlparse(self.base_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api-m.sandbox.paypal.com"
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise PaymentConfigurationError(
                "PayPal integration is restricted to https://api-m.sandbox.paypal.com."
            )

    def _request(self, method, path, *, payload=None, request_id=None):
        try:
            token_response = self.session.post(
                f"{self.base_url}/v1/oauth2/token",
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
                headers={"Accept": "application/json"},
                timeout=15,
            )
            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            if request_id:
                headers["PayPal-Request-Id"] = request_id
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            status_code = getattr(getattr(error, "response", None), "status_code", None)
            raise PayPalRequestError(
                "PayPal Sandbox request failed.", status_code=status_code
            ) from error
        except (KeyError, ValueError) as error:
            raise PayPalRequestError(
                "PayPal Sandbox returned an invalid response."
            ) from error

    def create_order(self, *, campaign_id, amount, currency, return_url, cancel_url):
        request_id = str(uuid4())
        order = self._request(
            "POST",
            "/v2/checkout/orders",
            request_id=request_id,
            payload={
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "reference_id": campaign_id,
                        "custom_id": campaign_id,
                        "amount": {"currency_code": currency, "value": amount},
                    }
                ],
                "application_context": {
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                    "user_action": "PAY_NOW",
                },
            },
        )
        approval_url = next(
            (
                link.get("href")
                for link in order.get("links", [])
                if link.get("rel") == "approve" and link.get("href")
            ),
            None,
        )
        if not order.get("id") or not approval_url:
            raise PayPalRequestError(
                "PayPal did not return an order ID and approval URL."
            )
        approval = urlparse(approval_url)
        if approval.scheme != "https" or approval.hostname != "www.sandbox.paypal.com":
            raise PayPalRequestError(
                "PayPal returned an approval URL outside Sandbox checkout."
            )
        return order, approval_url, request_id

    def capture_order(self, order_id):
        return self._request(
            "POST",
            f"/v2/checkout/orders/{quote(order_id, safe='')}/capture",
            request_id=f"resqpay-capture-{order_id}",
            payload={},
        )


def validate_capture_response(result, *, order_id, campaign_id, amount, currency):
    """Validate successful capture and bind it to the saved order details."""
    if not isinstance(result, dict):
        raise ValueError("PayPal returned an invalid capture response.")
    if result.get("id") != order_id:
        raise ValueError("PayPal capture order ID does not match the stored order.")
    if result.get("status") != "COMPLETED":
        raise ValueError("PayPal has not confirmed a completed payment.")

    purchase_units = result.get("purchase_units") or []
    if len(purchase_units) != 1 or not isinstance(purchase_units[0], dict):
        raise ValueError("PayPal returned an unexpected purchase unit count.")
    purchase = purchase_units[0]
    if (
        purchase.get("reference_id") != campaign_id
        or purchase.get("custom_id") != campaign_id
    ):
        raise ValueError("PayPal order does not belong to the expected campaign.")

    payments = purchase.get("payments") or {}
    if not isinstance(payments, dict):
        raise ValueError("PayPal returned invalid payment details.")
    captures = payments.get("captures") or []
    if not isinstance(captures, list) or any(
        not isinstance(item, dict) for item in captures
    ):
        raise ValueError("PayPal returned invalid capture details.")
    completed = [
        item for item in captures
        if item.get("status") == "COMPLETED" and item.get("id")
    ]
    if len(completed) != 1:
        raise ValueError("PayPal did not return exactly one completed capture.")
    capture = completed[0]
    captured_amount = capture.get("amount") or {}
    try:
        captured_value = float(captured_amount.get("value"))
        expected_value = float(amount)
    except (TypeError, ValueError) as error:
        raise ValueError("PayPal returned an invalid capture amount.") from error
    if (
        captured_amount.get("currency_code") != currency
        or not math.isfinite(captured_value)
        or captured_value <= 0
        or round(captured_value, 2) != round(expected_value, 2)
    ):
        raise ValueError(
            "PayPal capture amount or currency does not match the stored donation."
        )
    return {
        "transaction_id": capture["id"],
        "amount": f"{captured_value:.2f}",
        "currency": currency,
        "status": "COMPLETED",
    }
