"""An in-memory stand-in for the PayPal sandbox, so the whole app runs and is testable without credentials.
It mimics the shapes of PayPal's REST responses and webhook events, and signs events with an HMAC (clearly NOT PayPal's real signature scheme).
Anything produced here is labelled 'simulated' everywhere it is shown."""
from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import time
import uuid


class FakeGateway:
    mode = "fake"

    def __init__(self, secret: str = "ajo-simulated-webhook-secret"):
        self.secret = secret.encode()
        self.plans: dict[str, dict] = {}
        self.subs: dict[str, dict] = {}
        self.payouts: dict[str, dict] = {}
        self.sender_batches: dict[str, str] = {}
        self.invoices: dict[str, dict] = {}
        self.calls: list[tuple[str, dict]] = []
        self.fail_payouts = False
        self._n = itertools.count(1)

    def _id(self, p: str) -> str:
        return f"SBX-{p}-{next(self._n):04d}{uuid.uuid4().hex[:4].upper()}"

    def create_plan(self, name, amount, currency, interval_days):
        pid = self._id("PLAN"); self.plans[pid] = dict(name=name, amount=amount, currency=currency, interval_days=interval_days); self.calls.append(("create_plan", self.plans[pid])); return pid

    def create_subscription(self, plan_id, email, name):
        sid = self._id("SUB"); self.subs[sid] = dict(plan_id=plan_id, email=email, name=name, status="APPROVAL_PENDING"); self.calls.append(("create_subscription", self.subs[sid]))
        return {"id": sid, "status": "APPROVAL_PENDING", "approve_url": f"https://sandbox.example/approve/{sid}"}

    def create_payout(self, sender_batch_id, items):
        # PayPal rejects a reused sender_batch_id; returning the original batch makes a retry harmless.
        if sender_batch_id in self.sender_batches:
            b = self.payouts[self.sender_batches[sender_batch_id]]
            return {"batch_id": b["batch_id"], "status": b["status"], "duplicate": True}
        bid = self._id("PAYOUT"); status = "DENIED" if self.fail_payouts else "SUCCESS"
        self.payouts[bid] = dict(batch_id=bid, status=status, items=items, sender_batch_id=sender_batch_id); self.sender_batches[sender_batch_id] = bid
        self.calls.append(("create_payout", self.payouts[bid])); return {"batch_id": bid, "status": status, "duplicate": False}

    def get_payout(self, batch_id):
        return self.payouts[batch_id]

    def create_invoice(self, email, amount, currency, note, number):
        iid = self._id("INV"); self.invoices[iid] = dict(id=iid, email=email, amount=amount, currency=currency, note=note, number=number, status="DRAFT", reminders=0)
        self.calls.append(("create_invoice", self.invoices[iid])); return {"id": iid, "status": "DRAFT"}

    def send_invoice(self, invoice_id):
        self.invoices[invoice_id]["status"] = "SENT"; self.calls.append(("send_invoice", {"id": invoice_id}))

    def remind_invoice(self, invoice_id, note):
        self.invoices[invoice_id]["reminders"] += 1; self.calls.append(("remind_invoice", {"id": invoice_id, "note": note}))

    # ---- webhooks ----
    def sign(self, raw: bytes, ts: str) -> str:
        return hmac.new(self.secret, ts.encode() + b"." + raw, hashlib.sha256).hexdigest()

    def emit(self, event_type: str, resource: dict, event_id: str | None = None) -> tuple[bytes, dict[str, str]]:
        ev = {"id": event_id or f"WH-{uuid.uuid4().hex[:14].upper()}", "event_version": "1.0", "event_type": event_type, "resource": resource, "simulated": True}
        raw = json.dumps(ev).encode(); ts = str(int(time.time()))
        return raw, {"x-ajo-sim-time": ts, "x-ajo-sim-signature": self.sign(raw, ts)}

    def verify_webhook(self, headers, raw):
        h = {k.lower(): v for k, v in headers.items()}
        sig, ts = h.get("x-ajo-sim-signature", ""), h.get("x-ajo-sim-time", "")
        return bool(sig and ts) and hmac.compare_digest(sig, self.sign(raw, ts))

    # ---- convenience event builders (shapes follow PayPal's documented events; to be checked against the live sandbox) ----
    def subscription_activated(self, subscription_id: str, event_id: str | None = None):
        """What PayPal sends when the subscriber approves the subscription at PayPal."""
        if subscription_id in self.subs:
            self.subs[subscription_id]["status"] = "ACTIVE"
        return self.emit("BILLING.SUBSCRIPTION.ACTIVATED", {"id": subscription_id, "status": "ACTIVE"}, event_id)

    def payment_completed(self, subscription_id: str, amount: float, currency: str = "USD", event_id: str | None = None):
        return self.emit("PAYMENT.SALE.COMPLETED", {"id": self._id("SALE"), "billing_agreement_id": subscription_id, "state": "completed", "amount": {"total": f"{amount:.2f}", "currency": currency}}, event_id)

    def payment_failed(self, subscription_id: str, failed_count: int = 1, event_id: str | None = None):
        return self.emit("BILLING.SUBSCRIPTION.PAYMENT.FAILED", {"id": subscription_id, "status": "ACTIVE", "billing_info": {"failed_payments_count": failed_count}}, event_id)

    def invoice_paid(self, invoice_id: str, amount: float, event_id: str | None = None):
        return self.emit("INVOICING.INVOICE.PAID", {"invoice": {"id": invoice_id, "status": "PAID", "amount": {"value": f"{amount:.2f}"}}}, event_id)
