"""The real PayPal and model clients, exercised against a mocked HTTP transport. This checks request shapes against PayPal's public docs;
it does NOT prove they work against the live sandbox, which needs credentials (see README)."""
import json

import httpx
import pytest

from ajo.ai.llm import AnthropicLLM, OpenAICompatLLM, make_llm
from ajo.config import Settings
from ajo.paypal.base import make_gateway
from ajo.paypal.real import PayPalError, RealGateway


def gateway(handler, **kw):
    s = Settings(paypal_mode="sandbox", paypal_client_id="id", paypal_client_secret="secret", paypal_webhook_id="WH-1", **kw)
    g = RealGateway(s)
    g.http = httpx.Client(base_url=s.paypal_base, transport=httpx.MockTransport(handler))
    return g


def router(seen):
    def h(req: httpx.Request):
        seen.append(req)
        p = req.url.path
        if p == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "TOK", "expires_in": 3000})
        if p == "/v1/catalogs/products":
            return httpx.Response(201, json={"id": "PROD-1"})
        if p == "/v1/billing/plans":
            return httpx.Response(201, json={"id": "P-1"})
        if p == "/v1/billing/subscriptions":
            return httpx.Response(201, json={"id": "I-SUB", "status": "APPROVAL_PENDING", "links": [{"rel": "approve", "href": "https://pp/approve"}]})
        if p == "/v1/payments/payouts" and req.method == "POST":
            return httpx.Response(201, json={"batch_header": {"payout_batch_id": "BATCH-1", "batch_status": "PENDING"}})
        if p == "/v1/payments/payouts/BATCH-1":
            return httpx.Response(200, json={"batch_header": {"batch_status": "SUCCESS"}, "items": [{}]})
        if p == "/v2/invoicing/invoices":
            return httpx.Response(201, json={"href": "https://api-m.sandbox.paypal.com/v2/invoicing/invoices/INV2-ABCD"})
        if p.endswith("/send") or p.endswith("/remind"):
            return httpx.Response(202, json={})
        if p == "/v1/notifications/verify-webhook-signature":
            return httpx.Response(200, json={"verification_status": "FAILURE" if json.loads(req.content)["webhook_event"].get("id") == "BAD" else "SUCCESS"})
        return httpx.Response(404, json={"name": "NOT_FOUND"})
    return h


def test_oauth_and_plan_and_subscription():
    seen: list[httpx.Request] = []
    g = gateway(router(seen))
    plan = g.create_plan("Circle", 50, "USD", 14)
    sub = g.create_subscription(plan, "a@b.co", "Amara Okafor")
    assert plan == "P-1" and sub == {"id": "I-SUB", "status": "APPROVAL_PENDING", "approve_url": "https://pp/approve"}
    assert seen[0].url.path == "/v1/oauth2/token" and seen[0].headers["authorization"].startswith("Basic ")
    plan_req = next(r for r in seen if r.url.path == "/v1/billing/plans")
    body = json.loads(plan_req.content)
    assert plan_req.headers["authorization"] == "Bearer TOK" and body["product_id"] == "PROD-1"
    cyc = body["billing_cycles"][0]
    assert cyc["frequency"] == {"interval_unit": "DAY", "interval_count": 14} and cyc["pricing_scheme"]["fixed_price"] == {"value": "50.00", "currency_code": "USD"}
    assert len([r for r in seen if r.url.path == "/v1/oauth2/token"]) == 1          # token is cached


def test_payout_body_and_idempotency_header():
    seen: list[httpx.Request] = []
    g = gateway(router(seen))
    r = g.create_payout("ajo-g-c1-amara-v3", [{"receiver_email": "amara@x.co", "amount": 250, "currency": "USD", "note": "Ajo cycle 1", "sender_item_id": "i1"}])
    req = next(x for x in seen if x.url.path == "/v1/payments/payouts")
    body = json.loads(req.content)
    assert r == {"batch_id": "BATCH-1", "status": "PENDING", "duplicate": False}
    assert req.headers["paypal-request-id"] == "ajo-g-c1-amara-v3" and body["sender_batch_header"]["sender_batch_id"] == "ajo-g-c1-amara-v3"
    assert body["items"][0] == {"recipient_type": "EMAIL", "amount": {"value": "250.00", "currency": "USD"}, "receiver": "amara@x.co", "note": "Ajo cycle 1", "sender_item_id": "i1"}
    assert g.get_payout("BATCH-1")["status"] == "SUCCESS"


def test_invoice_create_send_remind():
    seen: list[httpx.Request] = []
    g = gateway(router(seen))
    inv = g.create_invoice("sam@x.co", 50, "USD", "Missed", "AJO-1")
    g.send_invoice(inv["id"]); g.remind_invoice(inv["id"], "hello")
    paths = [(r.method, r.url.path) for r in seen if "invoicing" in r.url.path]
    assert inv["id"] == "INV2-ABCD" and paths == [("POST", "/v2/invoicing/invoices"), ("POST", "/v2/invoicing/invoices/INV2-ABCD/send"), ("POST", "/v2/invoicing/invoices/INV2-ABCD/remind")]
    assert json.loads(next(r for r in seen if r.url.path.endswith("/remind")).content)["send_to_recipient"] is True


def test_webhook_verification_maps_success_and_failure():
    seen: list[httpx.Request] = []
    g = gateway(router(seen))
    hdr = {"paypal-auth-algo": "SHA256withRSA", "paypal-cert-url": "https://c", "paypal-transmission-id": "t", "paypal-transmission-sig": "s", "paypal-transmission-time": "now"}
    assert g.verify_webhook(hdr, b'{"id": "WH"}')
    sent = json.loads(seen[-1].content)
    assert sent["webhook_id"] == "WH-1" and sent["webhook_event"] == {"id": "WH"} and sent["transmission_id"] == "t"
    assert not g.verify_webhook(hdr, b'{"id": "BAD"}')
    assert not g.verify_webhook(hdr, b"not json")


def test_http_errors_become_paypal_errors():
    g = gateway(lambda req: httpx.Response(401, json={"error": "invalid_client"}) if "oauth2" in req.url.path else httpx.Response(404))
    with pytest.raises(PayPalError):
        g.create_plan("x", 1, "USD", 7)


def test_sandbox_mode_requires_credentials():
    with pytest.raises(RuntimeError):
        make_gateway(Settings(paypal_mode="sandbox"))


def test_llm_clients_parse_and_never_raise():
    ok = httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "```json\n{\"contribution\": 60}\n```"}}]}))
    s = Settings(llm="openai_compat", llm_api_key="k", llm_model="m", llm_base_url="https://llm.test/v1")
    c = OpenAICompatLLM(s); c.http = httpx.Client(transport=ok)
    assert c.json("sys", "usr") == {"contribution": 60}
    c.http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert c.json("sys", "usr") is None
    a = AnthropicLLM(Settings(llm="anthropic", llm_api_key="k", llm_model="m"))
    a.http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"content": [{"text": "noise {\"kind\": \"swap\"} noise"}]})))
    assert a.json("s", "u") == {"kind": "swap"}
    a.http = httpx.Client(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("down"))))
    assert a.json("s", "u") is None
    assert make_llm(Settings(llm="none")) is None and make_llm(Settings(llm="anthropic")) is None
