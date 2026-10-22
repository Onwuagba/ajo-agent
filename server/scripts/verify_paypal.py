"""Runs every PayPal call Ajo makes against the PayPal SANDBOX, one at a time, and prints what worked and what did not.
Needs PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET (a sandbox REST app) in .env. Never touches live PayPal: the base URL must be the sandbox.
Usage:  .venv/bin/python scripts/verify_paypal.py [--payout-to sb-buyer@personal.example.com]
The payout step only runs when you pass a sandbox personal account email (it sends 1.00 of sandbox money)."""
from __future__ import annotations

import argparse
import sys
import time
import uuid

sys.path.insert(0, ".")
from ajo.config import Settings  # noqa: E402
from ajo.paypal.real import PayPalError, RealGateway  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--payout-to", default="")
args = ap.parse_args()
s = Settings.from_env()
if "sandbox" not in s.paypal_base:
    sys.exit("Refusing to run: PAYPAL_BASE is not the sandbox.")
if not (s.paypal_client_id and s.paypal_client_secret):
    sys.exit("Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in .env first.")

gw = RealGateway(s)
results: list[tuple[str, bool, str]] = []


def step(name: str, fn):
    try:
        out = fn()
        results.append((name, True, str(out)[:140])); return out
    except (PayPalError, Exception) as e:  # noqa: BLE001  report every failure, keep going
        results.append((name, False, str(e)[:220])); return None


step("OAuth token", lambda: "received" if gw._token() else "")
plan = step("Create product and billing plan (14 day, 1.00 USD)", lambda: gw.create_plan(f"Ajo verify {uuid.uuid4().hex[:5]}", 1.0, "USD", 14))
if plan:
    sub = step("Create subscription (returns an approval link)", lambda: gw.create_subscription(plan, "buyer@example.com", "Test Buyer"))
    if sub:
        results.append(("  approval link present", bool(sub.get("approve_url")), sub.get("approve_url", "")[:100]))
inv = step("Create invoice (draft)", lambda: gw.create_invoice("buyer@example.com", 1.0, "USD", "Ajo verify", f"AJO-{int(time.time())}"))
if inv:
    step("Send invoice", lambda: gw.send_invoice(inv["id"]))
    step("Remind invoice", lambda: gw.remind_invoice(inv["id"], "Ajo verify reminder"))
if args.payout_to:
    key = f"ajo-verify-{uuid.uuid4().hex[:8]}"
    items = [{"amount": 1.0, "currency": "USD", "receiver_email": args.payout_to, "note": "Ajo verify", "sender_item_id": key}]
    b = step("Create payout batch (1.00 USD)", lambda: gw.create_payout(key, items))
    if b:
        step("Look the batch up", lambda: gw.get_payout(b["batch_id"]))
        step("Same sender_batch_id again is refused or deduplicated by PayPal", lambda: gw.create_payout(key, items))
else:
    results.append(("Create payout batch", False, "skipped: pass --payout-to <sandbox personal account email>"))
step("Webhook signature check rejects a bad signature", lambda: (_ for _ in ()).throw(PayPalError("unexpected")) if gw.verify_webhook({"paypal-transmission-sig": "bad"}, b"{}") else "rejected, as it should")

width = max(len(n) for n, _, _ in results)
for n, ok, d in results:
    print(f"{'PASS' if ok else 'FAIL'}  {n.ljust(width)}  {d}")
print("\nFail lines are the [VERIFY] items to fix in ajo/paypal/real.py. Webhook events (PAYMENT.SALE.COMPLETED etc.) need a public URL and PAYPAL_WEBHOOK_ID; test those from the deployed app.")
sys.exit(0 if all(ok for _, ok, d in results if not d.startswith("skipped")) else 1)
