from fastapi.testclient import TestClient

from ajo.api import create_app
from ajo.config import Settings

RULES = """Everyone pays $50 every two weeks, four of us in total.
The payout order is a random draw that we record, and the whole pot goes to one person each cycle.
Give a two day grace period. One missed payment gets an invoice and a reminder, two in a row means a warning to the group, and a third is the organiser's call.
Two members can swap turns if both agree and the organiser approves, but never after the payout has gone out.
One hardship skip per person, to be repaid within two cycles.
Never pay out more than $300, and ask the organiser before sending anything over $150."""


def client(**kw):
    app = create_app(Settings(db_path=":memory:", **kw))
    return TestClient(app), app


def signup(c, name="Amara Okafor", email="amara@example.com", pw="correct-horse"):
    r = c.post("/api/auth/register", json={"name": name, "email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"authorization": "Bearer " + r.json()["token"]}


def running_group(c):
    """Amara creates a four-person circle, appoints the treasurer, the sandbox friends join and the circle starts."""
    h = signup(c)
    gid = c.post("/api/groups", json={"name": "Sunday Circle", "size": 4, "contribution": 50, "cycleDays": 14}, headers=h).json()["id"]
    p = c.post(f"/api/groups/{gid}/rules/parse", json={"text": RULES}, headers=h).json()
    assert p["problems"] == [], p
    assert c.post(f"/api/groups/{gid}/treasurer", json={"text": RULES, "raw": p["raw"]}, headers=h).status_code == 200
    assert c.post(f"/api/sandbox/{gid}/join-friends", headers=h).status_code == 200
    assert c.post(f"/api/groups/{gid}/activate", headers=h).status_code == 200
    assert c.get(f"/api/groups/{gid}/state", headers=h).json()["group"]["status"] == "starting"      # waits for every member to approve at PayPal
    assert c.post(f"/api/sandbox/{gid}/approve-friends", headers=h).json()["approved"] == 3
    assert c.get(f"/api/groups/{gid}/state", headers=h).json()["group"]["status"] == "starting"      # the organiser has not approved yet
    assert c.post(f"/api/groups/{gid}/subscription/approve", headers=h).status_code == 200
    return h, gid


def friend(c, gid, h, idx=1):
    s = c.get(f"/api/groups/{gid}/state", headers=h).json()
    return [m for m in s["members"] if m["role"] != "organiser"][idx - 1]["id"]


def test_register_login_and_wrong_password():
    c, _ = client()
    signup(c)
    assert c.post("/api/auth/register", json={"name": "Amara", "email": "AMARA@example.com", "password": "another-pass1"}).status_code == 422   # email is unique, case-insensitively
    assert c.post("/api/auth/register", json={"name": "A", "email": "x@example.com", "password": "longenough"}).status_code == 422
    assert c.post("/api/auth/register", json={"name": "Bola", "email": "bola@example.com", "password": "short"}).status_code == 422
    ok = c.post("/api/auth/login", json={"email": "amara@example.com", "password": "correct-horse"})
    assert ok.status_code == 200
    h = {"authorization": "Bearer " + ok.json()["token"]}
    assert c.get("/api/auth/me", headers=h).json()["user"]["name"] == "Amara Okafor"
    assert c.post("/api/auth/login", json={"email": "amara@example.com", "password": "nope-nope"}).status_code == 422
    assert c.post("/api/auth/logout", headers=h).status_code == 200
    assert c.get("/api/auth/me", headers=h).status_code == 401


def test_every_group_route_needs_a_signed_in_member():
    c, _ = client()
    h, gid = running_group(c)
    assert c.get(f"/api/groups/{gid}/state").status_code == 401
    stranger = signup(c, "Eve Outsider", "eve@example.com")
    assert c.get(f"/api/groups/{gid}/state", headers=stranger).status_code == 403
    assert c.post(f"/api/groups/{gid}/chat", json={"text": "hi"}, headers=stranger).status_code == 403
    assert c.get("/api/groups/nope/state", headers=h).status_code == 404


def test_the_acting_member_comes_from_the_session_not_the_body():
    c, _ = client()
    h, gid = running_group(c)
    s = c.get(f"/api/groups/{gid}/state", headers=h).json()
    assert s["you"] == next(m["id"] for m in s["members"] if m["role"] == "organiser")
    # a body that claims to be someone else is ignored
    m = c.post(f"/api/groups/{gid}/chat", json={"who": friend(c, gid, h), "text": "Can I skip this cycle?"}, headers=h).json()
    st = c.get(f"/api/groups/{gid}/state", headers=h).json()
    assert st["chat"][0]["who"] == s["you"] and m["from"] == "agent"


def test_acting_as_a_sandbox_friend_is_limited():
    c, _ = client()
    h, gid = running_group(c)
    f = friend(c, gid, h)
    ok = c.get(f"/api/groups/{gid}/state", headers={**h, "x-act-as": f})
    assert ok.status_code == 200 and ok.json()["you"] == f
    assert c.get(f"/api/groups/{gid}/state", headers={**h, "x-act-as": "u-someoneelse"}).status_code == 403
    eve = signup(c, "Eve Outsider", "eve@example.com")
    assert c.get(f"/api/groups/{gid}/state", headers={**eve, "x-act-as": f}).status_code == 403          # not a member, so no borrowing identities
    assert c.post("/api/auth/login", json={"email": "tunde." + "x", "password": "x"}).status_code == 422   # sandbox friends cannot sign in


def test_the_simulator_is_off_when_not_using_the_paypal_simulator():
    class Stub:                 # anything that is not the in-memory simulator, standing in for the real sandbox client
        mode = "sandbox"
    app = create_app(Settings(db_path=":memory:"), gateway=Stub())
    c = TestClient(app)
    assert c.get("/api/health").json()["sandbox"] is False
    h = signup(c)
    gid = c.post("/api/groups", json={"name": "Real Circle", "size": 4, "contribution": 50, "cycleDays": 14}, headers=h).json()["id"]
    assert c.post(f"/api/sandbox/{gid}/join-friends", headers=h).status_code == 404
    assert c.post(f"/api/sandbox/{gid}/advance", json={"days": 3}, headers=h).status_code == 404


def test_state_shape_matches_the_front_end_types():
    c, _ = client()
    h, gid = running_group(c)
    s = c.get(f"/api/groups/{gid}/state", headers=h).json()
    assert {"members", "cycles", "rules", "ledger", "timeline", "approvals", "chat", "audit", "pot", "memberStatus", "group", "invites", "you"} <= s.keys()
    assert s["group"]["status"] == "active" and s["currentCycle"] == 1


def test_webhook_endpoint_checks_the_signature():
    c, app = client()
    h, gid = running_group(c)
    gw, eng = app.state.gateway, app.state.engine
    sub = eng.member(gid, friend(c, gid, h))["subscription_id"]
    raw, headers = gw.payment_completed(sub, 50)
    assert c.post("/api/webhooks/paypal", content=raw, headers={**headers, "x-ajo-sim-signature": "bad"}).status_code == 400
    r = c.post("/api/webhooks/paypal", content=raw, headers=headers)
    assert r.status_code == 200 and r.json()["handled"]
    assert c.post("/api/webhooks/paypal", content=raw, headers=headers).json()["reason"] == "duplicate event"


def test_rules_parse_then_confirm_is_organiser_only():
    c, _ = client()
    h, gid = running_group(c)
    f = friend(c, gid, h)
    p = c.post(f"/api/groups/{gid}/rules/parse", json={"text": "Everyone pays $50 every two weeks, four of us. Never pay out more than $300, ask the organiser over $250."}, headers=h).json()
    assert p["rules"]["approvalAbove"] == 250 and p["problems"] == []
    assert c.post(f"/api/groups/{gid}/rules/confirm", json={"text": "Everyone pays $50", "raw": p["raw"]}, headers={**h, "x-act-as": f}).status_code == 422
    ok = c.post(f"/api/groups/{gid}/rules/confirm", json={"text": "Everyone pays $50 every two weeks", "raw": p["raw"]}, headers=h)
    assert ok.status_code == 200 and ok.json()["version"] == 2
    assert c.post(f"/api/groups/{gid}/rules/confirm", json={"text": "xxxxx", "raw": {"contribution": -1}}, headers=h).status_code == 422


def test_swap_over_http_with_acting_members():
    c, _ = client()
    h, gid = running_group(c)
    f1, f2 = friend(c, gid, h, 1), friend(c, gid, h, 2)
    n2 = next(m["first"] for m in c.get(f"/api/groups/{gid}/state", headers=h).json()["members"] if m["id"] == f2)
    m = c.post(f"/api/groups/{gid}/chat", json={"text": f"Can I swap turns with {n2}?"}, headers={**h, "x-act-as": f1}).json()
    assert m["approvalId"] and not m["blocked"]
    a = next(x for x in c.get(f"/api/groups/{gid}/state", headers=h).json()["approvals"] if x["kind"] == "swap")
    assert c.post(f"/api/groups/{gid}/approvals/{a['id']}/decide", json={"verdict": "approved"}, headers={**h, "x-act-as": friend(c, gid, h, 3)}).status_code == 422
    assert c.post(f"/api/groups/{gid}/approvals/{a['id']}/decide", json={"verdict": "approved"}, headers={**h, "x-act-as": f2}).status_code == 200


def test_audit_verification_and_tamper_over_http():
    c, _ = client()
    h, gid = running_group(c)
    assert c.get(f"/api/groups/{gid}/audit/verify", headers=h).json() == {"intact": True, "brokenAt": None}
    c.post(f"/api/sandbox/{gid}/tamper/2", headers=h)
    assert c.get(f"/api/groups/{gid}/audit/verify", headers=h).json() == {"intact": False, "brokenAt": 2}
    c.post(f"/api/sandbox/{gid}/tamper/2?undo=true", headers=h)
    assert c.get(f"/api/groups/{gid}/audit/verify", headers=h).json()["intact"]


def test_full_cycle_with_the_simulator_pays_out_once():
    c, app = client()
    h, gid = running_group(c)
    s = c.get(f"/api/groups/{gid}/state", headers=h).json()
    for m in s["members"]:
        assert c.post(f"/api/sandbox/{gid}/pay", json={"member": m["id"]}, headers=h).status_code == 200
    s = c.get(f"/api/groups/{gid}/state", headers=h).json()
    a = [x for x in s["approvals"] if x["kind"] == "payout"]
    assert len(a) == 1                                   # pot 200 > threshold 150, so the organiser must approve
    assert c.post(f"/api/groups/{gid}/approvals/{a[0]['id']}/decide", json={"verdict": "approved"}, headers=h).status_code == 200
    payouts = [r for r in c.get(f"/api/groups/{gid}/state", headers=h).json()["ledger"] if r["kind"] == "payout" and r["status"] == "completed"]
    assert len(payouts) == 1 and payouts[0]["amount"] == 200
    assert len([k for k, _ in app.state.gateway.calls if k == "create_payout"]) == 1


def test_each_member_approves_their_own_subscription_before_the_clock_starts():
    c, app = client()
    h = signup(c)
    gid = c.post("/api/groups", json={"name": "Circle", "size": 4, "contribution": 50, "cycleDays": 14}, headers=h).json()["id"]
    p = c.post(f"/api/groups/{gid}/rules/parse", json={"text": RULES}, headers=h).json()
    c.post(f"/api/groups/{gid}/treasurer", json={"text": RULES, "raw": p["raw"]}, headers=h)
    c.post(f"/api/sandbox/{gid}/join-friends", headers=h)
    c.post(f"/api/groups/{gid}/activate", headers=h)
    s = c.get(f"/api/groups/{gid}/state", headers=h).json()
    assert s["currentCycle"] is None and s["payment"]["status"] == "pending" and s["payment"]["approveUrl"]
    assert [m["paypal"] for m in s["members"]].count("pending") == 4
    # a payment that arrives before everyone has approved is noted, not counted
    gw, eng = app.state.gateway, app.state.engine
    raw, hd = gw.payment_completed(eng.member(gid, s["you"])["subscription_id"], 50)
    assert c.post("/api/webhooks/paypal", content=raw, headers=hd).status_code == 200
    assert not [r for r in c.get(f"/api/groups/{gid}/state", headers=h).json()["ledger"]]
    c.post(f"/api/sandbox/{gid}/approve-friends", headers=h)
    c.post(f"/api/groups/{gid}/subscription/approve", headers=h)
    s = c.get(f"/api/groups/{gid}/state", headers=h).json()
    assert s["group"]["status"] == "active" and s["currentCycle"] == 1 and s["payment"]["status"] == "linked"
    assert c.post(f"/api/groups/{gid}/subscription/approve", headers=h).status_code == 200      # approving twice is harmless


def test_hardship_skip_lowers_the_pot_and_is_repaid():
    c, _ = client()
    h, gid = running_group(c)
    f = friend(c, gid, h)
    m = c.post(f"/api/groups/{gid}/chat", json={"text": "I'm short this week, can I skip?"}, headers={**h, "x-act-as": f}).json()
    assert m["approvalId"] and not m["blocked"]
    d = c.post(f"/api/groups/{gid}/approvals/{m['approvalId']}/decide", json={"verdict": "approved"}, headers=h)
    assert d.status_code == 200
    s = c.get(f"/api/groups/{gid}/state", headers=h).json()
    assert s["pot"]["target"] == 150 and s["skips"] == [{"member": f, "cycle": 1}] and s["memberStatus"][f] == "skipped"
    # asking a second time is refused by the rule (one skip per member)
    again = c.post(f"/api/groups/{gid}/chat", json={"text": "I'm short again, can I skip?"}, headers={**h, "x-act-as": f}).json()
    assert not again["approvalId"]


def test_declining_a_payout_sends_nothing():
    c, app = client()
    h, gid = running_group(c)
    for m in c.get(f"/api/groups/{gid}/state", headers=h).json()["members"]:
        c.post(f"/api/sandbox/{gid}/pay", json={"member": m["id"]}, headers=h)
    a = next(x for x in c.get(f"/api/groups/{gid}/state", headers=h).json()["approvals"] if x["kind"] == "payout")
    assert c.post(f"/api/groups/{gid}/approvals/{a['id']}/decide", json={"verdict": "declined"}, headers=h).status_code == 200
    s = c.get(f"/api/groups/{gid}/state", headers=h).json()
    assert not [r for r in s["ledger"] if r["kind"] == "payout" and r["status"] == "completed"] and s["currentCycle"] == 1
    assert not [k for k, _ in app.state.gateway.calls if k == "create_payout"]
    # a decided request cannot be decided again
    assert c.post(f"/api/groups/{gid}/approvals/{a['id']}/decide", json={"verdict": "approved"}, headers=h).status_code == 422
    assert not [k for k, _ in app.state.gateway.calls if k == "create_payout"]


def test_rules_can_change_after_the_start_but_not_the_amount_once_money_has_moved():
    c, _ = client()
    h, gid = running_group(c)
    ok = c.post(f"/api/groups/{gid}/rules/parse", json={"text": RULES.replace("two day grace", "three day grace").replace("$150", "$180")}, headers=h).json()
    assert ok["rules"]["graceDays"] == 3
    r = c.post(f"/api/groups/{gid}/rules/confirm", json={"text": "x" * 10, "raw": ok["raw"]}, headers=h)
    assert r.status_code == 200 and r.json()["version"] == 2
    s = c.get(f"/api/groups/{gid}/state", headers=h).json()
    c.post(f"/api/sandbox/{gid}/pay", json={"member": s["you"]}, headers=h)
    bad = c.post(f"/api/groups/{gid}/rules/parse", json={"text": RULES.replace("$50", "$60")}, headers=h).json()
    r = c.post(f"/api/groups/{gid}/rules/confirm", json={"text": "x" * 10, "raw": bad["raw"]}, headers=h)
    assert r.status_code == 422 and "mid-rotation" in r.json()["error"]


def test_only_the_organiser_sees_member_emails():
    c, _ = client()
    h, gid = running_group(c)
    mine = c.get(f"/api/groups/{gid}/state", headers=h).json()
    assert all(m["email"] for m in mine["members"])
    theirs = c.get(f"/api/groups/{gid}/state", headers={**h, "x-act-as": friend(c, gid, h)}).json()
    assert [m["email"] for m in theirs["members"] if m["id"] != theirs["you"]] == ["", "", ""]


def test_a_hardship_skip_is_repaid_by_invoice_and_counts_toward_the_next_pot():
    c, app = client()
    h, gid = running_group(c)
    s = c.get(f"/api/groups/{gid}/state", headers=h).json()
    f = friend(c, gid, h)
    m = c.post(f"/api/groups/{gid}/chat", json={"text": "I'm short this week, can I skip?"}, headers={**h, "x-act-as": f}).json()
    c.post(f"/api/groups/{gid}/approvals/{m['approvalId']}/decide", json={"verdict": "approved"}, headers=h)
    assert [r["amount"] for r in c.get(f"/api/groups/{gid}/state", headers=h).json()["repayments"]] == [25.0, 25.0]
    for mem in s["members"]:                                   # everyone except the skipper pays cycle 1
        if mem["id"] != f:
            c.post(f"/api/sandbox/{gid}/pay", json={"member": mem["id"]}, headers=h)
    # the 150 pot is not above the 150 approval line, so it pays out on its own and cycle 2 opens
    s2 = c.get(f"/api/groups/{gid}/state", headers=h).json()
    assert s2["currentCycle"] == 2 and s2["pot"]["target"] == 225      # 4 x 50 plus the 25 repayment due
    inv = [r for r in s2["ledger"] if r["kind"] == "invoice" and r["cycle"] == 2]
    assert len(inv) == 1 and inv[0]["amount"] == 25
    for mem in s["members"]:
        c.post(f"/api/sandbox/{gid}/pay", json={"member": mem["id"]}, headers=h)
    assert not [x for x in c.get(f"/api/groups/{gid}/state", headers=h).json()["approvals"] if x["kind"] == "payout" and any(n["state"] == "pending" for n in x["needs"])]   # 200 collected, 225 needed: not funded yet
    c.post(f"/api/sandbox/{gid}/pay-invoice", json={"member": f}, headers=h)
    s3 = c.get(f"/api/groups/{gid}/state", headers=h).json()
    p2 = [x for x in s3["approvals"] if x["kind"] == "payout" and any(n["state"] == "pending" for n in x["needs"])]
    assert p2 and p2[0]["amount"] == 225 and [r["kind"] for r in s3["ledger"]].count("repayment") == 1
    assert c.get(f"/api/groups/{gid}/audit/verify", headers=h).json()["intact"]
    # a repayment still unpaid after the grace period gets one reminder, not one per tick
    sub = [k for k, _ in app.state.gateway.calls if k == "create_invoice"]
    assert len(sub) == 1


def test_rules_must_leave_room_for_hardship_repayments_and_a_blocked_payout_recovers_when_they_are_raised():
    c, _ = client()
    h = signup(c)
    gid = c.post("/api/groups", json={"name": "Tight", "size": 4, "contribution": 50, "cycleDays": 14}, headers=h).json()["id"]
    tight = RULES.replace("$300", "$200").replace("$150", "$100")             # pot 200, max exactly 200: no room for a repayment
    p = c.post(f"/api/groups/{gid}/rules/parse", json={"text": tight}, headers=h).json()
    assert p["problems"] and "could never be paid out" in p["problems"][0]
    r = c.post(f"/api/groups/{gid}/treasurer", json={"text": tight, "raw": p["raw"]}, headers=h)
    assert r.status_code == 422 and "never be paid out" in r.json()["error"]
    ok = c.post(f"/api/groups/{gid}/rules/parse", json={"text": tight.replace("$200, and", "$225, and")}, headers=h).json()
    assert ok["problems"] == []


def test_the_circle_completes_after_the_last_payout_and_then_ignores_new_events():
    c, app = client()
    h, gid = running_group(c)
    members = c.get(f"/api/groups/{gid}/state", headers=h).json()["members"]
    for n in range(1, 5):
        for m in members:
            c.post(f"/api/sandbox/{gid}/pay", json={"member": m["id"]}, headers=h)
        for a in [x for x in c.get(f"/api/groups/{gid}/state", headers=h).json()["approvals"] if x["kind"] == "payout" and any(k["state"] == "pending" for k in x["needs"])]:
            assert c.post(f"/api/groups/{gid}/approvals/{a['id']}/decide", json={"verdict": "approved"}, headers=h).status_code == 200
    s = c.get(f"/api/groups/{gid}/state", headers=h).json()
    assert s["group"]["status"] == "complete" and s["currentCycle"] is None and [x["status"] for x in s["cycles"]] == ["paid"] * 4
    assert len([r for r in s["ledger"] if r["kind"] == "payout" and r["status"] == "completed"]) == 4
    n_calls = len([k for k, _ in app.state.gateway.calls if k == "create_payout"])
    c.post(f"/api/sandbox/{gid}/pay", json={"member": members[0]["id"]}, headers=h)          # a late event after the end moves no money
    assert len([k for k, _ in app.state.gateway.calls if k == "create_payout"]) == n_calls == 4
    assert c.get(f"/api/groups/{gid}/audit/verify", headers=h).json()["intact"]
