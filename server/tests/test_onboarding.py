import pytest

from ajo import accounts
from ajo.clock import Clock
from ajo.engine import Engine, RuleError
from ajo.paypal.fake import FakeGateway
from ajo.rules import RuleSet
from ajo.sandbox import Sandbox
from ajo.store import Store


@pytest.fixture
def world():
    gw, clk = FakeGateway(), Clock(1_760_000_000_000)
    e = Engine(Store(":memory:"), gw, clk)
    org = accounts.register(e.s, "Amara Okafor", "amara@example.com", "correct-horse", clk.now())
    return e, gw, Sandbox(e, gw), org


def start(e, sb, org, gid="g1"):
    e.activate(gid, org["id"]); sb.approve_friends(gid); sb.approve_subscription(gid, org["id"])


def open_four(e, org):
    e.open_group("g1", "Sunday Circle", org, 4, 50, 14)
    return e.rules("g1")


def test_a_new_group_is_forming_with_no_subscriptions_or_cycles(world):
    e, gw, sb, org = world
    open_four(e, org)
    s = e.snapshot("g1")
    assert s["group"]["status"] == "forming" and s["cycles"] == [] and s["currentCycle"] is None
    assert [k for k, _ in gw.calls] == []                    # no PayPal plan or subscription before the roster is final
    assert [m["role"] for m in s["members"]] == ["organiser"]


def test_invites_fill_the_roster_and_cannot_overfill_it(world):
    e, _, _, org = world
    open_four(e, org)
    for n in ("Tunde", "Fatima", "Chidi"):
        e.invite("g1", org["id"], n)
    with pytest.raises(RuleError, match="spoken for"):
        e.invite("g1", org["id"], "One too many")
    e.revoke_invite("g1", org["id"], e.snapshot("g1")["invites"][0]["code"])
    e.invite("g1", org["id"], "Replacement")


def test_only_the_organiser_manages_invites(world):
    e, _, sb, org = world
    open_four(e, org)
    sb.join_friends("g1")                                    # fills the roster
    friend = next(m for m in e.members("g1") if m["role"] != "organiser")
    with pytest.raises(RuleError):
        e.invite("g1", friend["id"], "Someone")


def test_accepting_an_invite_joins_once_and_the_code_is_then_spent(world):
    e, _, _, org = world
    open_four(e, org)
    code = e.invite("g1", org["id"], "Tunde", "tunde@example.com")["code"]
    info = e.invite_info(code)
    assert info["group"] == "Sunday Circle" and info["organiser"] == "Amara Okafor" and info["status"] == "pending"
    tunde = accounts.register(e.s, "Tunde Adeyemi", "tunde@example.com", "correct-horse", e.clock.now())
    assert e.accept_invite(code, tunde) == "g1"
    with pytest.raises(RuleError, match="no longer open"):
        e.accept_invite(code, accounts.register(e.s, "Other", "other@example.com", "correct-horse", e.clock.now()))
    assert e.invite_info(code)["status"] == "accepted"


def test_cannot_start_until_the_treasurer_is_appointed_and_the_roster_is_full(world):
    e, _, sb, org = world
    rules = open_four(e, org)
    with pytest.raises(RuleError, match="appoint the treasurer"):
        e.activate("g1", org["id"])
    e.appoint_treasurer("g1", org["id"], "Everyone pays $50 every two weeks, four of us in total.", rules)
    with pytest.raises(RuleError, match="1 of 4 have joined"):
        e.activate("g1", org["id"])
    sb.join_friends("g1")
    e.activate("g1", org["id"])
    s = e.snapshot("g1")
    assert s["group"]["status"] == "starting" and s["currentCycle"] is None and len(s["cycles"]) == 4
    assert all(m["subscription_id"] for m in e.members("g1"))
    sb.approve_friends("g1"); assert e.status("g1") == "starting"
    sb.approve_subscription("g1", org["id"])
    assert e.snapshot("g1")["group"]["status"] == "active" and e.snapshot("g1")["currentCycle"] == 1


def test_only_the_organiser_appoints_and_starts(world):
    e, _, sb, org = world
    rules = open_four(e, org)
    sb.join_friends("g1")
    friend = next(m["id"] for m in e.members("g1") if m["role"] != "organiser")
    with pytest.raises(RuleError, match="only the organiser"):
        e.appoint_treasurer("g1", friend, "x", rules)
    e.appoint_treasurer("g1", org["id"], "x", rules)
    with pytest.raises(RuleError, match="only the organiser"):
        e.activate("g1", friend)


def test_rules_that_make_payouts_impossible_are_refused(world):
    e, _, sb, org = world
    rules = open_four(e, org)
    with pytest.raises(RuleError, match="maximum single payout"):
        e.appoint_treasurer("g1", org["id"], "x", rules.model_copy(update={"max_payout": 100}))
    sb.join_friends("g1")
    with pytest.raises(RuleError, match="already joined"):
        e.appoint_treasurer("g1", org["id"], "x", RuleSet(members=2))


def test_a_running_group_cannot_be_reopened(world):
    e, _, sb, org = world
    rules = open_four(e, org)
    e.appoint_treasurer("g1", org["id"], "x", rules); sb.join_friends("g1"); start(e, sb, org)
    with pytest.raises(RuleError):
        e.activate("g1", org["id"])
    with pytest.raises(RuleError):
        e.invite("g1", org["id"], "Late")
    with pytest.raises(RuleError):
        e.appoint_treasurer("g1", org["id"], "x", rules)


def test_audit_chain_covers_onboarding(world):
    e, _, sb, org = world
    rules = open_four(e, org)
    e.appoint_treasurer("g1", org["id"], "x", rules); sb.join_friends("g1"); start(e, sb, org)
    actions = [a["action"] for a in e.snapshot("g1")["audit"]]
    assert actions[0] == "Group opened" and "Treasurer appointed" in actions and actions.count("Member joined") == 3 and "Order drawn" in actions
    assert e.verify_audit("g1") is None


def test_late_payment_ladder_through_the_simulator(world):
    e, _, sb, org = world
    rules = open_four(e, org)
    e.appoint_treasurer("g1", org["id"], "x", rules); sb.join_friends("g1"); start(e, sb, org)
    late = [m["id"] for m in e.members("g1") if m["role"] != "organiser"][0]
    for m in e.members("g1"):
        if m["id"] != late:
            sb.pay("g1", m["id"])
    sb.fail("g1", late)
    assert sb.advance("g1", 3)                                # grace period over: the agent invoices
    assert e.member_status("g1", late, 1) == "invoiced"
    sb.pay_invoice("g1", late)
    assert e.member_status("g1", late, 1) == "paid"


def test_removing_a_member_before_the_start_reopens_their_place(world):
    e, _, sb, org = world
    open_four(e, org)
    sb.join_friends("g1")
    gone = next(m for m in e.members("g1") if m["role"] != "organiser")
    e.remove_member("g1", org["id"], gone["id"])
    assert len(e.members("g1")) == 3
    e.invite("g1", org["id"], "Replacement")                 # the freed place can be offered again
    with pytest.raises(RuleError, match="only the organiser"):
        e.remove_member("g1", next(m["id"] for m in e.members("g1") if m["role"] != "organiser"), org["id"])
    with pytest.raises(RuleError, match="you are the organiser"):
        e.remove_member("g1", org["id"], org["id"])


def test_the_roster_is_fixed_once_the_circle_has_started(world):
    e, _, sb, org = world
    rules = open_four(e, org)
    e.appoint_treasurer("g1", org["id"], "x", rules); sb.join_friends("g1"); start(e, sb, org)
    with pytest.raises(RuleError, match="roster is fixed"):
        e.remove_member("g1", org["id"], next(m["id"] for m in e.members("g1") if m["role"] != "organiser"))
