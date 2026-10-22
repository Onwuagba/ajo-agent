"""Real PayPal sandbox client (REST, OAuth 2.0 client credentials). Endpoint paths and bodies follow PayPal's public docs.
STATUS: written against the docs, NOT yet exercised against a live sandbox account. Every method here is a [VERIFY] item until it has run once."""
from __future__ import annotations

import base64
import json
import time

import httpx

from ..config import Settings


class PayPalError(RuntimeError):
    pass


class RealGateway:
    mode = "sandbox"

    def __init__(self, s: Settings):
        self.s = s
        self.http = httpx.Client(base_url=s.paypal_base, timeout=30)
        self._tok: tuple[str, float] | None = None
        self._product: str | None = None

    def _token(self) -> str:
        if self._tok and self._tok[1] > time.time() + 30:
            return self._tok[0]
        basic = base64.b64encode(f"{self.s.paypal_client_id}:{self.s.paypal_client_secret}".encode()).decode()
        r = self.http.post("/v1/oauth2/token", data={"grant_type": "client_credentials"}, headers={"Authorization": f"Basic {basic}"})
        if r.status_code != 200:
            raise PayPalError(f"token request failed: {r.status_code} {r.text[:200]}")
        j = r.json(); self._tok = (j["access_token"], time.time() + int(j.get("expires_in", 300)))
        return self._tok[0]

    def _call(self, method: str, path: str, body: dict | None = None, request_id: str | None = None) -> dict:
        h = {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"}
        if request_id:
            h["PayPal-Request-Id"] = request_id            # PayPal's own idempotency header
        r = self.http.request(method, path, headers=h, content=json.dumps(body) if body is not None else None)
        if r.status_code >= 300:
            raise PayPalError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else {}

    def create_plan(self, name, amount, currency, interval_days):
        if not self._product:
            self._product = self._call("POST", "/v1/catalogs/products", {"name": "Ajo contributions", "type": "SERVICE", "category": "SOFTWARE"}, request_id="ajo-product")["id"]
        plan = {"product_id": self._product, "name": name, "status": "ACTIVE",
                "billing_cycles": [{"frequency": {"interval_unit": "DAY", "interval_count": interval_days}, "tenure_type": "REGULAR", "sequence": 1, "total_cycles": 0,
                                    "pricing_scheme": {"fixed_price": {"value": f"{amount:.2f}", "currency_code": currency}}}],
                "payment_preferences": {"auto_bill_outstanding": False, "payment_failure_threshold": 2}}
        return self._call("POST", "/v1/billing/plans", plan)["id"]

    def create_subscription(self, plan_id, email, name):
        first, _, last = name.partition(" ")
        j = self._call("POST", "/v1/billing/subscriptions", {"plan_id": plan_id, "subscriber": {"email_address": email, "name": {"given_name": first, "surname": last or first}},
                       "application_context": {"user_action": "SUBSCRIBE_NOW", "return_url": "https://example.com/return", "cancel_url": "https://example.com/cancel"}})
        approve = next((l["href"] for l in j.get("links", []) if l.get("rel") == "approve"), "")
        return {"id": j["id"], "status": j.get("status", "APPROVAL_PENDING"), "approve_url": approve}

    def create_payout(self, sender_batch_id, items):
        body = {"sender_batch_header": {"sender_batch_id": sender_batch_id, "email_subject": "Your Ajo payout"},
                "items": [{"recipient_type": "EMAIL", "amount": {"value": f"{i['amount']:.2f}", "currency": i["currency"]}, "receiver": i["receiver_email"], "note": i.get("note", ""),
                           "sender_item_id": i["sender_item_id"]} for i in items]}
        j = self._call("POST", "/v1/payments/payouts", body, request_id=sender_batch_id)
        return {"batch_id": j["batch_header"]["payout_batch_id"], "status": j["batch_header"]["batch_status"], "duplicate": False}

    def get_payout(self, batch_id):
        j = self._call("GET", f"/v1/payments/payouts/{batch_id}")
        return {"batch_id": batch_id, "status": j["batch_header"]["batch_status"], "items": j.get("items", [])}

    def create_invoice(self, email, amount, currency, note, number):
        j = self._call("POST", "/v2/invoicing/invoices", {"detail": {"invoice_number": number, "currency_code": currency, "note": note},
                       "primary_recipients": [{"billing_info": {"email_address": email}}],
                       "items": [{"name": "Missed Ajo contribution", "quantity": "1", "unit_amount": {"currency_code": currency, "value": f"{amount:.2f}"}}]})
        return {"id": j["href"].rstrip("/").split("/")[-1], "status": "DRAFT"}

    def send_invoice(self, invoice_id):
        self._call("POST", f"/v2/invoicing/invoices/{invoice_id}/send", {"send_to_recipient": True})

    def remind_invoice(self, invoice_id, note):
        self._call("POST", f"/v2/invoicing/invoices/{invoice_id}/remind", {"subject": "Reminder: your Ajo contribution", "note": note, "send_to_recipient": True})

    def verify_webhook(self, headers, raw):
        h = {k.lower(): v for k, v in headers.items()}
        try:
            j = self._call("POST", "/v1/notifications/verify-webhook-signature", {"auth_algo": h.get("paypal-auth-algo"), "cert_url": h.get("paypal-cert-url"),
                           "transmission_id": h.get("paypal-transmission-id"), "transmission_sig": h.get("paypal-transmission-sig"), "transmission_time": h.get("paypal-transmission-time"),
                           "webhook_id": self.s.paypal_webhook_id, "webhook_event": json.loads(raw)})
        except (PayPalError, ValueError):
            return False
        return j.get("verification_status") == "SUCCESS"
