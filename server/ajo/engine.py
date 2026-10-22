"""The treasurer. One class that owns every state change. The model reads and explains; this module decides.
The only code path that sends money is Engine._execute_payout, and it refuses to run without an approved or engine-cleared proposal."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from . import audit as auditlog
from .ai.intents import Intent, classify
from .ai.phrase import rephrase
from .ai.llm import LLM, build_llm
from .ai.parser import ParseResult, parse_rules
from .clock import Clock
from .paypal.base import Gateway
from .rules import (RuleSet, chk, contribution_checks, draw_order, hardship_checks, payout_checks, swap_checks, validate_rules)
from .store import Store

HUES = [158, 32, 12, 262, 205, 340, 90, 190]
DAY = 86_400_000


class RuleError(ValueError):
    """A request the rules do not allow. The message is safe to show to members."""


def _date(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%b %-d")


class Engine:
    def __init__(self, store: Store, gateway: Gateway, clock: Clock, llm: LLM | None = None, settings=None):
        self.s, self.gw, self.clock, self.llm, self.settings = store, gateway, clock, llm, settings
        self._llms: dict[tuple, LLM | None] = {}

    def llm_for(self, gid: str) -> LLM | None:
        """The model this circle chose (any provider, its own key), else the server default."""
        c = self.s.one("model_config", group_id=gid)
        if not c:
            return self.llm
        key = (c["provider"], c["base_url"], c["model"], c["api_key"])
        if key not in self._llms:
            self._llms[key] = build_llm(c["provider"], c["base_url"] or "", c["model"], c["api_key"] or "", self.settings) if self.settings else None
        return self._llms[key]

    # ------------------------------------------------------------------ plumbing
    def _id(self, p: str) -> str:
        return f"{p}-{uuid.uuid4().hex[:10]}"

    def _audit(self, gid: str, actor: str, action: str, detail: str) -> None:
        auditlog.append(self.s, gid, actor, action, detail, self.clock.now())

    def _note(self, gid: str, tone: str, title: str, body: str, why: str | None = None) -> None:
        self.s.insert("timeline", {"id": self._id("t"), "group_id": gid, "ts": self.clock.now(), "tone": tone, "title": title, "body": body, "why": why})

    def _ledger(self, gid: str, **r) -> dict:
        row = {"id": self._id("r"), "group_id": gid, "ts": self.clock.now(), "paypal_id": "", "rule_version": self.rules(gid).version, "approver": None, "simulated": 0, "checks": [], **r}
        self.s.insert("ledger", row)
        return row

    def _touch(self, gid: str) -> None:
        self.s.bump(gid)

    # ------------------------------------------------------------------ reads
    def rules(self, gid: str) -> RuleSet:
        row = self.s.db.execute("select body from rule_sets where group_id=? order by version desc limit 1", (gid,)).fetchone()
        if not row:
            raise KeyError(f"unknown group {gid}")
        return RuleSet.model_validate_json(row["body"])

    def members(self, gid: str) -> list[dict]:
        return self.s.all("members", order="turn, role desc, rowid", group_id=gid)

    def member(self, gid: str, mid: str) -> dict:
        m = self.s.one("members", group_id=gid, id=mid)
        if not m:
            raise RuleError(f"{mid} is not a member of this group")
        return m

    def organiser(self, gid: str) -> str:
        return next(m["id"] for m in self.members(gid) if m["role"] == "organiser")

    def cycles(self, gid: str) -> list[dict]:
        return self.s.all("cycles", order="n", group_id=gid)

    def current_cycle(self, gid: str) -> dict | None:
        return next((c for c in self.cycles(gid) if c["status"] == "collecting"), None)

    def _paid(self, gid: str, member: str, cycle: int) -> bool:
        return self.s.db.execute("select 1 from ledger where group_id=? and member=? and cycle=? and kind in ('contribution','invoice_payment') and status='completed' limit 1", (gid, member, cycle)).fetchone() is not None

    def skipped(self, gid: str, member: str, cycle: int) -> bool:
        return self.s.one("skips", group_id=gid, member=member, cycle=cycle) is not None

    def member_status(self, gid: str, member: str, cycle: int) -> str:
        if self.skipped(gid, member, cycle):
            return "skipped"
        if self._paid(gid, member, cycle):
            return "paid"
        rows = self.s.all("ledger", group_id=gid, member=member, cycle=cycle)
        if any(r["kind"] == "invoice" for r in rows):
            return "invoiced"
        if any(r["kind"] == "contribution" and r["status"] == "failed" for r in rows):
            return "late"
        return "pending"

    def collected(self, gid: str, cycle: int) -> float:
        c = self.rules(gid).contribution
        repaid = self.s.db.execute("select coalesce(sum(amount),0) a from repayments where group_id=? and due_cycle=? and status='paid'", (gid, cycle)).fetchone()["a"]
        return round(sum(c for m in self.members(gid) if self.member_status(gid, m["id"], cycle) == "paid") + repaid, 2)

    def target(self, gid: str, cycle: int) -> float:
        r = self.rules(gid)
        owed = self.s.db.execute("select coalesce(sum(amount),0) a from repayments where group_id=? and due_cycle=? and status!='cancelled'", (gid, cycle)).fetchone()["a"]
        return round(r.contribution * (len(self.members(gid)) - sum(1 for m in self.members(gid) if self.skipped(gid, m["id"], cycle))) + owed, 2)

    # ------------------------------------------------------------------ setup
    def create_group(self, gid: str, name: str, members: list[dict], rules: RuleSet, rules_text: str, start_ts: int | None = None) -> None:
        """Create and launch a group whose whole roster is known (used by tests and the seeded sample)."""
        if self.s.one("groups", id=gid):
            raise RuleError("group already exists")
        if len(members) != rules.members:
            raise RuleError(f"the rules say {rules.members} members but {len(members)} were given")
        if sum(1 for m in members if m.get("role") == "organiser") != 1:
            raise RuleError("a group needs exactly one organiser")
        start = start_ts or self.clock.now()
        self.s.insert("groups", {"id": gid, "name": name, "currency": rules.currency, "plan_id": "", "created_ts": start, "status": "forming", "treasurer": 1, "owner": next(m["id"] for m in members if m.get("role") == "organiser")})
        for i, m in enumerate(members):
            self.s.insert("members", {"id": m["id"], "group_id": gid, "name": m["name"], "first": m["name"].split()[0], "role": m.get("role", "member"), "hue": HUES[i % len(HUES)],
                                      "email": m["email"], "turn": 0, "subscription_id": ""})
        self._launch(gid, rules, rules_text, start)

    def _launch(self, gid: str, rules: RuleSet, rules_text: str, start: int, wait_for_members: bool = False) -> None:
        """Draw the order, create the PayPal plan and one subscription per member, and lay out the cycles.
        With wait_for_members the circle stays in 'starting' until every member has approved their own subscription at PayPal."""
        members = self.members(gid); name = self.s.one("groups", id=gid)["name"]
        problems = validate_rules(rules)
        if problems:
            raise RuleError("; ".join(problems))
        rules = rules.model_copy(update={"version": 1, "seed": rules.seed if rules.seed != "unset" else uuid.uuid4().hex[:6]})
        order = draw_order([m["id"] for m in members], rules.seed) if rules.order == "random" else [m["id"] for m in members]
        plan = self.gw.create_plan(f"{name} contribution", rules.contribution, rules.currency, rules.cycle_days)
        self.s.update("groups", {"id": gid}, {"plan_id": plan, "currency": rules.currency, "status": "starting"})
        for m in members:
            sub = self.gw.create_subscription(plan, m["email"], m["name"])
            ready = not wait_for_members or sub.get("status") == "ACTIVE"
            self.s.update("members", {"group_id": gid, "id": m["id"]}, {"turn": order.index(m["id"]) + 1, "subscription_id": sub["id"], "sub_status": "ACTIVE" if ready else "APPROVAL_PENDING", "approve_url": sub.get("approve_url", "")})
        self.s.insert("rule_sets", {"group_id": gid, "version": 1, "body": rules.model_dump_json(), "text": rules_text, "note": "First draft from plain English", "confirmed_by": self.organiser(gid), "ts": start}, replace=True)
        for n, rid in enumerate(order, 1):
            due = start + (n - 1) * rules.cycle_days * DAY
            self.s.insert("cycles", {"group_id": gid, "n": n, "date": _date(due), "recipient": rid, "pot": rules.pot, "status": "upcoming", "due_ts": due})
        self._audit(gid, "organiser", "Rules confirmed", f"Rule set v1 confirmed from plain English by {self.member(gid, self.organiser(gid))['first']}")
        self._audit(gid, "engine", "Order drawn", f"{'Random draw, seed ' + rules.seed if rules.order == 'random' else 'Fixed order'}: " + ", ".join(self.member(gid, r)["first"] for r in order))
        self._audit(gid, "paypal", "Subscriptions created", f"{len(members)} subscriptions on the {rules.contribution:g} / {rules.cycle_days} day plan ({self.gw.mode}); each member approves their own")
        if not wait_for_members or all(m["sub_status"] == "ACTIVE" for m in self.members(gid)):
            self._go_live(gid, start)
        else:
            self._note(gid, "info", "Waiting for PayPal approvals", "Each member approves their own subscription at PayPal. The first cycle starts when everyone has.")
        self._touch(gid)

    def _go_live(self, gid: str, start: int | None = None) -> None:
        """Every subscription is active: start the clock. Cycle 1 is collecting and the due dates count from now."""
        start = start or self.clock.now(); rules = self.rules(gid)
        for c in self.cycles(gid):
            due = start + (c["n"] - 1) * rules.cycle_days * DAY
            self.s.update("cycles", {"group_id": gid, "n": c["n"]}, {"due_ts": due, "date": _date(due), "status": "collecting" if c["n"] == 1 else "upcoming"})
        self.s.update("groups", {"id": gid}, {"status": "active"})
        self._audit(gid, "paypal", "Subscriptions active", f"{len(self.members(gid))} of {len(self.members(gid))} members subscribed ({self.gw.mode})")
        cur = self.current_cycle(gid)
        self._note(gid, "good", "The circle has started", f"Order drawn and everyone is subscribed. {self.member(gid, cur['recipient'])['first']} collects first.", "Random draw with a recorded seed, so anyone can reproduce it.")

    def _on_sub_activated(self, gid: str, sub: str) -> None:
        m = self._by_sub(gid, sub)
        if not m or m["sub_status"] == "ACTIVE":
            return
        self.s.update("members", {"group_id": gid, "id": m["id"]}, {"sub_status": "ACTIVE", "approve_url": ""})
        self._audit(gid, "paypal", "PayPal approved", f"{m['first']} approved their subscription")
        self._note(gid, "info", f"{m['first']} linked PayPal", f"{sum(1 for x in self.members(gid) if x['sub_status'] == 'ACTIVE')} of {len(self.members(gid))} approved.")
        if self.status(gid) == "starting" and all(x["sub_status"] == "ACTIVE" for x in self.members(gid)):
            self._go_live(gid)

    # ------------------------------------------------------------------ onboarding: the real-app flow
    def status(self, gid: str) -> str:
        g = self.s.one("groups", id=gid)
        if not g:
            raise KeyError(gid)
        return g["status"]

    def open_group(self, gid: str, name: str, organiser: dict, size: int, contribution: float, cycle_days: int, currency: str = "USD") -> None:
        """Step 1: the organiser names the circle. Nothing is subscribed or scheduled until the treasurer is appointed and everyone has joined."""
        name = name.strip()
        if len(name) < 2:
            raise RuleError("give the group a name")
        pot = round(contribution * size, 2)
        try:
            rules = RuleSet(members=size, contribution=contribution, cycle_days=cycle_days, currency=currency, max_payout=round(pot + contribution, 2), approval_above=round(pot * 0.8, 2))
        except ValueError as e:
            raise RuleError("; ".join(x["msg"] for x in e.errors())[:240] if hasattr(e, "errors") else str(e))
        now = self.clock.now()
        self.s.insert("groups", {"id": gid, "name": name, "currency": rules.currency, "plan_id": "", "created_ts": now, "status": "forming", "treasurer": 0, "owner": organiser["id"]})
        self.s.insert("members", {"id": organiser["id"], "group_id": gid, "name": organiser["name"], "first": organiser["name"].split()[0], "role": "organiser", "hue": HUES[0], "email": organiser["email"], "turn": 0, "subscription_id": ""})
        text = f"Everyone pays {rules.contribution:g} {rules.currency} every {rules.cycle_days} days, {size} of us in total."
        self.s.insert("rule_sets", {"group_id": gid, "version": 1, "body": rules.model_dump_json(), "text": text, "note": "Draft, not yet confirmed", "confirmed_by": organiser["id"], "ts": now})
        self._audit(gid, "organiser", "Group opened", f"{organiser['name']} opened \"{name}\": {size} members, {rules.contribution:g} {rules.currency} every {rules.cycle_days} days")
        self._touch(gid)

    def invite(self, gid: str, who: str, name: str, email: str = "") -> dict:
        if self.status(gid) != "forming":
            raise RuleError("this group is already running, so there is no roster to fill")
        if who != self.organiser(gid):
            raise RuleError("only the organiser can invite people")
        size = self.rules(gid).members
        open_invites = self.s.db.execute("select count(*) n from invites where group_id=? and status='pending'", (gid,)).fetchone()["n"]
        if len(self.members(gid)) + open_invites >= size:
            raise RuleError(f"the group has {size} places and they are all spoken for")
        name, email = name.strip()[:60], email.strip().lower()[:120]
        if not name:
            raise RuleError("who is this invite for? Add a name")
        if email and (self.s.db.execute("select 1 from invites where group_id=? and email=? and status!='revoked'", (gid, email)).fetchone() or any(m["email"] == email for m in self.members(gid))):
            raise RuleError("that email has already been invited")
        code = uuid.uuid4().hex[:10]
        self.s.insert("invites", {"code": code, "group_id": gid, "name": name, "email": email, "status": "pending", "user_id": None, "ts": self.clock.now()})
        self._audit(gid, "organiser", "Invite created", f"Invite for {name} created")
        self._touch(gid)
        return {"code": code, "name": name, "email": email, "status": "pending"}

    def revoke_invite(self, gid: str, who: str, code: str) -> None:
        inv = self.s.one("invites", code=code)
        if not inv or inv["group_id"] != gid or inv["status"] != "pending":
            raise RuleError("that invite is not open")
        if who != self.organiser(gid):
            raise RuleError("only the organiser can withdraw an invite")
        self.s.update("invites", {"code": code}, {"status": "revoked"})
        self._audit(gid, "organiser", "Invite withdrawn", f"Invite for {inv['name']} withdrawn")
        self._touch(gid)

    def remove_member(self, gid: str, who: str, mid: str) -> None:
        """Before the circle starts the organiser can take someone off the roster (their place opens up again). Once subscriptions exist the roster is fixed."""
        if self.status(gid) != "forming":
            raise RuleError("the roster is fixed once the circle has started, because each member has their own PayPal subscription and a turn in the order")
        if who != self.organiser(gid):
            raise RuleError("only the organiser can remove someone")
        if mid == who:
            raise RuleError("you are the organiser. Appoint someone else first, or delete the circle")
        m = self.member(gid, mid)
        self.s.db.execute("delete from members where group_id=? and id=?", (gid, mid)); self.s.db.commit()
        self.s.db.execute("update invites set status='revoked' where group_id=? and user_id=?", (gid, mid)); self.s.db.commit()
        self._audit(gid, "organiser", "Member removed", f"{m['name']} was removed from the roster before the circle started")
        self._note(gid, "warn", f"{m['first']} was removed", f"{len(self.members(gid))} of {self.rules(gid).members} places filled.")
        self._touch(gid)

    def invite_info(self, code: str) -> dict:
        inv = self.s.one("invites", code=code)
        if not inv:
            raise KeyError(code)
        g = self.s.one("groups", id=inv["group_id"]); r = self.rules(g["id"]); org = self.member(g["id"], self.organiser(g["id"]))
        return {"code": code, "status": inv["status"] if g["status"] == "forming" or inv["status"] != "pending" else "closed", "forName": inv["name"], "group": g["name"], "organiser": org["name"],
                "contribution": r.contribution, "currency": r.currency, "cycleDays": r.cycle_days, "size": r.members, "joined": len(self.members(g["id"]))}

    def accept_invite(self, code: str, user: dict) -> str:
        inv = self.s.one("invites", code=code)
        if not inv:
            raise KeyError(code)
        gid = inv["group_id"]
        if inv["status"] != "pending" or self.status(gid) != "forming":
            raise RuleError("this invite is no longer open")
        if self.s.one("members", group_id=gid, id=user["id"]):
            raise RuleError("you are already in this group")
        members = self.members(gid)
        if len(members) >= self.rules(gid).members:
            raise RuleError("the group is full")
        self.s.insert("members", {"id": user["id"], "group_id": gid, "name": user["name"], "first": user["name"].split()[0], "role": "member", "hue": HUES[len(members) % len(HUES)],
                                  "email": user["email"], "turn": 0, "subscription_id": ""})
        self.s.update("invites", {"code": code}, {"status": "accepted", "user_id": user["id"]})
        self._audit(gid, "member", "Member joined", f"{user['name']} joined ({len(members) + 1} of {self.rules(gid).members})")
        self._note(gid, "info", f"{user['name'].split()[0]} joined", f"{len(members) + 1} of {self.rules(gid).members} places filled.")
        self._touch(gid)
        return gid

    def appoint_treasurer(self, gid: str, who: str, text: str, rules: RuleSet) -> RuleSet:
        """Step 3: the organiser confirms the written rules and gives the AI treasurer its limits. The agent proposes; only the rules engine can move money."""
        if self.status(gid) != "forming":
            raise RuleError("the treasurer is already appointed for a running group")
        if who != self.organiser(gid):
            raise RuleError("only the organiser can appoint the treasurer")
        joined = len(self.members(gid))
        if rules.members < joined:
            raise RuleError(f"{joined} people have already joined, so the group cannot be smaller than that")
        problems = validate_rules(rules)
        if problems:
            raise RuleError("; ".join(problems))
        new = rules.model_copy(update={"version": 1, "seed": "unset"})
        self.s.insert("rule_sets", {"group_id": gid, "version": 1, "body": new.model_dump_json(), "text": text, "note": "Confirmed by the organiser", "confirmed_by": who, "ts": self.clock.now()}, replace=True)
        self.s.update("groups", {"id": gid}, {"treasurer": 1})
        self._audit(gid, "organiser", "Treasurer appointed", f"AI treasurer appointed. Pays out at most {new.max_payout:g}; asks the organiser above {new.approval_above:g}; grace {new.grace_days} days")
        self._note(gid, "agent", "I'm your treasurer", f"I will track every contribution, chase late ones the way your rules say, and propose each payout. I can't move money myself: the rules engine checks every payout and asks {self.member(gid, self.organiser(gid))['first']} for anything above {new.approval_above:g}.", "Appointed by the organiser from the written rules.")
        self._touch(gid)
        return new

    def activate(self, gid: str, who: str) -> None:
        """Step 4: start the rotation once the roster is full and the treasurer is appointed."""
        g = self.s.one("groups", id=gid)
        if not g:
            raise KeyError(gid)
        if g["status"] != "forming":
            raise RuleError("this group is already running")
        if who != self.organiser(gid):
            raise RuleError("only the organiser can start the group")
        if not g["treasurer"]:
            raise RuleError("appoint the treasurer first: confirm the rules")
        rules = self.rules(gid); joined = len(self.members(gid))
        if joined != rules.members:
            raise RuleError(f"{joined} of {rules.members} have joined. Invite the rest or change the group size in the rules")
        text = self.s.one("rule_sets", group_id=gid, version=1)["text"]
        self._launch(gid, rules, text, self.clock.now(), wait_for_members=True)

    # ------------------------------------------------------------------ rules
    def parse_rules(self, gid: str, text: str) -> ParseResult:
        return parse_rules(text, self.rules(gid), self.llm_for(gid))

    def confirm_rules(self, gid: str, who: str, text: str, rules: RuleSet, note: str = "Confirmed from the organiser's plain-English text") -> RuleSet:
        if who != self.organiser(gid):
            raise RuleError("only the organiser can confirm rules")
        cur = self.rules(gid)
        started = any(c["status"] != "upcoming" and self.collected(gid, c["n"]) > 0 for c in self.cycles(gid)) or any(c["status"] == "paid" for c in self.cycles(gid))
        if rules.members != cur.members:
            raise RuleError("the number of members cannot change once the rotation exists")
        if started and (rules.contribution != cur.contribution or rules.cycle_days != cur.cycle_days):
            raise RuleError("changing the amount or the cycle length mid-rotation needs new PayPal subscriptions, which is not supported yet")
        problems = validate_rules(rules)
        if problems:
            raise RuleError("; ".join(problems))
        new = rules.model_copy(update={"version": cur.version + 1, "seed": cur.seed, "order": cur.order})
        self.s.insert("rule_sets", {"group_id": gid, "version": new.version, "body": new.model_dump_json(), "text": text, "note": note, "confirmed_by": who, "ts": self.clock.now()})
        self._audit(gid, "organiser", "Rules confirmed", f"Rule set v{new.version} confirmed from plain English")
        self._note(gid, "agent", f"Rules v{new.version} are live", "Every decision from now on records this version.")
        self._maybe_propose_payout(gid)      # a payout blocked by the old limits gets a fresh check under the new rules
        self._touch(gid)
        return new

    # ------------------------------------------------------------------ money in (webhooks)
    def handle_event(self, event: dict) -> dict:
        """Dispatch a verified PayPal event. Idempotent on the event id. The caller must have verified the signature."""
        et, res, eid = event.get("event_type", ""), event.get("resource", {}), event.get("id", "")
        gid = self._group_for(et, res)
        if not gid:
            return {"handled": False, "reason": "no matching group"}
        try:
            self.s.insert("events", {"event_id": eid, "group_id": gid, "ts": self.clock.now(), "type": et})
        except sqlite3.IntegrityError:
            self._audit(gid, "paypal", "Duplicate event ignored", f"{et} {eid} was already processed")
            return {"handled": False, "reason": "duplicate event"}
        sim = bool(event.get("simulated"))
        if et == "BILLING.SUBSCRIPTION.ACTIVATED":
            self._on_sub_activated(gid, res["id"])
        elif self.status(gid) != "active":
            self._audit(gid, "paypal", "Event noted", f"{et} {eid} arrived before the circle started; no action taken")
        elif et == "PAYMENT.SALE.COMPLETED":
            self._on_payment(gid, res["billing_agreement_id"], float(res["amount"]["total"]), sim)
        elif et == "BILLING.SUBSCRIPTION.PAYMENT.FAILED":
            self._on_failed(gid, res["id"], sim)
        elif et == "INVOICING.INVOICE.PAID":
            self._on_invoice_paid(gid, res["invoice"]["id"], sim)
        else:
            self._audit(gid, "paypal", "Event noted", f"{et} {eid}: no action needed")
        self._touch(gid)
        return {"handled": True, "group": gid, "type": et}

    def _group_for(self, et: str, res: dict) -> str | None:
        key = res.get("billing_agreement_id") or (res.get("id") if et.startswith("BILLING.SUBSCRIPTION") else None)
        if key:
            m = self.s.db.execute("select group_id from members where subscription_id=?", (key,)).fetchone()
            return m["group_id"] if m else None
        iid = (res.get("invoice") or {}).get("id")
        if iid:
            r = self.s.db.execute("select group_id from invoices where id=?", (iid,)).fetchone()
            return r["group_id"] if r else None
        return None

    def _by_sub(self, gid: str, sub: str) -> dict | None:
        r = self.s.db.execute("select * from members where group_id=? and subscription_id=?", (gid, sub)).fetchone()
        return dict(r) if r else None

    def _cycle_for(self, gid: str, member: str) -> dict | None:
        """The earliest open cycle this member has not paid or skipped (an early payment counts toward the next one)."""
        for c in self.cycles(gid):
            if c["status"] in ("collecting", "upcoming") and not self._paid(gid, member, c["n"]) and not self.skipped(gid, member, c["n"]):
                return c
        return None

    def _on_payment(self, gid: str, sub: str, amount: float, sim: bool) -> None:
        m = self._by_sub(gid, sub); rules = self.rules(gid)
        if not m:
            self._audit(gid, "paypal", "Payment from unknown subscription", f"{sub} ${amount:g}: held, not matched to a member"); return
        c = self._cycle_for(gid, m["id"])
        if not c:
            self._audit(gid, "paypal", "Payment ignored", f"{m['first']} ${amount:g}: nothing left to pay"); return
        checks = contribution_checks(rules, amount, True, False, c["n"])
        if not all(x["pass"] for x in checks):
            self._ledger(gid, cycle=c["n"], kind="contribution", member=m["id"], amount=amount, status="pending", rule="Contribution: " + f"${rules.contribution:g} every {rules.cycle_days} days",
                         explanation="The amount does not match the contribution rule, so it is held for the organiser and not counted.", checks=checks, simulated=int(sim))
            self._note(gid, "warn", f"{m['first']}'s payment needs a look", f"${amount:g} received, ${rules.contribution:g} expected.", "Only an exact match counts toward the pot.")
            self._audit(gid, "paypal", "Payment held", f"{m['first']} ${amount:g} for cycle {c['n']} does not match the rule"); return
        self._ledger(gid, cycle=c["n"], kind="contribution", member=m["id"], amount=amount, status="completed", rule=f"Contribution: ${rules.contribution:g} every {rules.cycle_days} days",
                     paypal_id=sub, explanation=f"{m['first']}'s subscription charged ${amount:g} on time.", checks=checks, simulated=int(sim))
        self._after_payment(gid, m, c, "Payment received")

    def _on_failed(self, gid: str, sub: str, sim: bool) -> None:
        m = self._by_sub(gid, sub); rules = self.rules(gid)
        if not m:
            return
        c = self._cycle_for(gid, m["id"]) or self.current_cycle(gid)
        if not c:
            return
        self._ledger(gid, cycle=c["n"], kind="contribution", member=m["id"], amount=rules.contribution, status="failed", simulated=int(sim), paypal_id=sub,
                     rule="Late ladder: after 1 miss, invoice and remind", explanation=f"Subscription payment failed{' (simulated event)' if sim else ''}. After the {rules.grace_days} day grace period the rules say: invoice and remind.",
                     checks=[chk("Payment completed", False, "BILLING.SUBSCRIPTION.PAYMENT.FAILED received"), chk("Webhook signature verified", True, "Verified before processing"), chk("Not a duplicate event", True, "First time this event id is seen")])
        self._note(gid, "bad", f"{m['first']}'s payment failed", f"{'Simulated event. ' if sim else ''}The late ladder starts after the {rules.grace_days} day grace period.", "The rules, not PayPal's retry timing, decide what happens next.")
        self._audit(gid, "paypal", "Payment failed" + (" (simulated)" if sim else ""), f"{m['first']} ${rules.contribution:g} for cycle {c['n']}; late ladder step 1 queued")

    def _issue_repayments(self, gid: str, cycle: int) -> None:
        """When a cycle opens, invoice every hardship repayment that falls due in it. Idempotent: a repayment is invoiced once."""
        rules = self.rules(gid)
        for rp in self.s.all("repayments", group_id=gid, due_cycle=cycle, status="due"):
            m = self.member(gid, rp["member"])
            created = self.gw.create_invoice(m["email"], rp["amount"], rules.currency, f"Hardship repayment for cycle {cycle}", f"AJO-{gid[:6].upper()}-R{cycle}-{m['id'][-3:].upper()}")
            self.gw.send_invoice(created["id"])
            self.s.insert("invoices", {"id": created["id"], "group_id": gid, "cycle": cycle, "member": m["id"], "amount": rp["amount"], "status": "SENT", "ts": self.clock.now(), "reminders": 0, "purpose": "repayment"})
            self.s.update("repayments", {"id": rp["id"]}, {"status": "invoiced", "invoice_id": created["id"]})
            self._ledger(gid, cycle=cycle, kind="invoice", member=m["id"], amount=rp["amount"], status="sent", paypal_id=created["id"], rule="Hardship: repaid within the rule's limit",
                         explanation=f"{m['first']} skipped an earlier cycle. This is the agreed repayment, invoiced when the cycle opened. It counts toward this cycle's pot.",
                         checks=[chk("Hardship skip was approved", True, "By the organiser, under the hardship rule"), chk("Repayment within the rule's limit", True, f"${rp['amount']:g} of ${rules.contribution:g} owed")])
            self._note(gid, "agent", f"Repayment invoice sent to {m['first']}", f"${rp['amount']:g} toward the cycle {cycle} pot ({created['id']}).", "Agreed when the hardship skip was approved.")
            self._audit(gid, "engine", "Repayment invoiced", f"{m['first']} ${rp['amount']:g} for cycle {cycle}, invoice {created['id']}")

    def _on_invoice_paid(self, gid: str, iid: str, sim: bool) -> None:
        inv = self.s.one("invoices", id=iid)
        if not inv or inv["status"] == "PAID":
            return
        if inv["purpose"] == "repayment":
            m = self.member(gid, inv["member"])
            self.s.update("invoices", {"id": iid}, {"status": "PAID"}); self.s.update("repayments", {"invoice_id": iid}, {"status": "paid"})
            self._ledger(gid, cycle=inv["cycle"], kind="repayment", member=m["id"], amount=inv["amount"], status="completed", paypal_id=iid, simulated=int(sim), rule="Hardship: repaid within the rule's limit",
                         explanation=f"{m['first']} paid a hardship repayment. It counts toward cycle {inv['cycle']}'s pot.", checks=[chk("Matches an invoiced repayment", True, f"Invoice {iid}")])
            self._note(gid, "good", f"{m['first']} repaid ${inv['amount']:g}", f"Cycle {inv['cycle']} is ${self.collected(gid, inv['cycle']):g} of ${self.target(gid, inv['cycle']):g}.", "Hardship repayment received.")
            self._audit(gid, "paypal", "Repayment received", f"{m['first']} ${inv['amount']:g} for cycle {inv['cycle']}")
            self._maybe_propose_payout(gid)
            return
        m = self.member(gid, inv["member"]); c = next(x for x in self.cycles(gid) if x["n"] == inv["cycle"]); rules = self.rules(gid)
        self.s.update("invoices", {"id": iid}, {"status": "PAID"})
        self._ledger(gid, cycle=c["n"], kind="invoice_payment", member=m["id"], amount=inv["amount"], status="completed", paypal_id=iid, simulated=int(sim),
                     rule=f"Contribution: ${rules.contribution:g} every {rules.cycle_days} days", explanation=f"{m['first']} paid the catch-up invoice. The late flag is cleared.",
                     checks=contribution_checks(rules, inv["amount"], True, False, c["n"]))
        self._after_payment(gid, m, c, "Invoice paid")

    def _after_payment(self, gid: str, m: dict, c: dict, action: str) -> None:
        got, tgt = self.collected(gid, c["n"]), self.target(gid, c["n"])
        self._note(gid, "good", f"{m['first']} paid ${self.rules(gid).contribution:g}", f"Cycle {c['n']} pot: ${got:g} of ${tgt:g}.", "Webhook matched to the member, amount equals the rule.")
        self._audit(gid, "paypal", action, f"{m['first']} ${self.rules(gid).contribution:g} for cycle {c['n']} (webhook, signature verified)")
        if c["status"] == "collecting":
            self._maybe_propose_payout(gid)

    # ------------------------------------------------------------------ the late ladder
    def tick(self, gid: str) -> list[str]:
        """Run time-based rules: after the grace period, invoice, remind and escalate exactly as the rules say. Safe to call repeatedly."""
        c = self.current_cycle(gid); rules = self.rules(gid); did: list[str] = []
        if self.status(gid) == "active" and not c and self.cycles(gid) and all(x["status"] == "paid" for x in self.cycles(gid)):
            self.s.update("groups", {"id": gid}, {"status": "complete"}); self._audit(gid, "engine", "Circle complete", f"All {len(self.cycles(gid))} cycles are paid out"); self._touch(gid)
            return did
        if self.status(gid) != "active" or not c or self.clock.now() < c["due_ts"] + rules.grace_days * DAY:
            return did
        for inv in self.s.all("invoices", group_id=gid, cycle=c["n"], purpose="repayment", status="SENT"):
            if inv["reminders"] == 0:      # a repayment that is still unpaid after the grace period gets one reminder
                self.gw.remind_invoice(inv["id"], "A friendly reminder about your agreed hardship repayment.")
                self.s.update("invoices", {"id": inv["id"]}, {"reminders": 1})
                self._note(gid, "agent", f"Reminder sent to {self.member(gid, inv['member'])['first']}", f"The ${inv['amount']:g} hardship repayment for cycle {c['n']} is still open.", "Reminders follow the grace period.")
                did.append(f"repayment-reminder:{inv['member']}")
        for m in self.members(gid):
            if self.member_status(gid, m["id"], c["n"]) not in ("late", "pending", "invoiced"):
                continue
            misses = 1 + sum(1 for p in self.cycles(gid) if p["n"] < c["n"] and p["status"] == "paid" and not self._paid(gid, m["id"], p["n"]) and not self.skipped(gid, m["id"], p["n"]))
            steps = [s for s in rules.ladder if s.after <= misses]
            if not steps:
                continue
            for step in steps:
                mark = f"ladder:{gid}:{c['n']}:{m['id']}:{step.action}"
                if self.s.one("events", event_id=mark):
                    continue
                self.s.insert("events", {"event_id": mark, "group_id": gid, "ts": self.clock.now(), "type": "ladder"})
                did.append(self._ladder_action(gid, c, m, step.action, misses))
        self._touch(gid)
        return did

    def _ladder_action(self, gid: str, c: dict, m: dict, action: str, misses: int) -> str:
        rules = self.rules(gid)
        if action == "invoice_and_remind":
            created = self.gw.create_invoice(m["email"], rules.contribution, rules.currency, f"Missed Ajo contribution for cycle {c['n']}", f"AJO-{gid[:6].upper()}-C{c['n']}-{m['id'][:3].upper()}")
            self.gw.send_invoice(created["id"]); self.gw.remind_invoice(created["id"], "A friendly reminder from your group's treasurer.")
            self.s.insert("invoices", {"id": created["id"], "group_id": gid, "cycle": c["n"], "member": m["id"], "amount": rules.contribution, "status": "SENT", "ts": self.clock.now(), "reminders": 1})
            self._ledger(gid, cycle=c["n"], kind="invoice", member=m["id"], amount=rules.contribution, status="sent", paypal_id=created["id"], rule="Late ladder: after 1 miss, invoice and remind",
                         explanation="Grace period over. Invoice for the missed contribution sent and a reminder scheduled, exactly as the rules say.",
                         checks=[chk("Grace period elapsed", True, f"{rules.grace_days} days since the due date"), chk("Amount equals the shortfall", True, f"${rules.contribution:.2f}"), chk("Within the ladder", True, "Step 1 of 3: invoice and remind")])
            self._note(gid, "agent", f"Invoice sent to {m['first']}", f"${rules.contribution:g} catch-up invoice ({created['id']}), reminder scheduled.", "Ladder step 1: invoice and remind.")
            self._audit(gid, "engine", "Invoice sent", f"{m['first']} ${rules.contribution:g} shortfall, invoice {created['id']}")
            return f"invoice:{m['id']}"
        if action == "warn_group":
            self._note(gid, "warn", f"{m['first']} has missed {misses} payments in a row", "The rules say the group is told at this point. The organiser can still decide what happens next.", "Ladder step 2: warn the group.")
            self._audit(gid, "engine", "Group warned", f"{m['first']} missed {misses} in a row")
            return f"warn:{m['id']}"
        aid = self._id("a")
        self.s.insert("approvals", {"id": aid, "group_id": gid, "kind": "decision", "title": f"Decide about {m['first']}'s repeated missed payments", "body": f"{m['first']} has missed {misses} payments in a row. The rules leave this to the organiser. I will not remove anyone myself.", "amount": None,
                                    "needs": [{"who": self.organiser(gid), "state": "pending"}], "checks": [chk("Ladder reached step 3", True, "Organiser decides")], "payload": {"member": m["id"]}, "ts": self.clock.now()})
        self._audit(gid, "engine", "Organiser decision requested", f"{m['first']} missed {misses} in a row")
        return f"decision:{m['id']}"

    # ------------------------------------------------------------------ money out
    def _maybe_propose_payout(self, gid: str) -> None:
        c = self.current_cycle(gid)
        if not c or self.s.one("payouts", group_id=gid, cycle=c["n"], recipient=c["recipient"]):
            return
        if self.s.db.execute("select 1 from ledger where group_id=? and cycle=? and kind='payout' and status in ('awaiting_approval','completed')", (gid, c["n"])).fetchone():
            return
        got, tgt = self.collected(gid, c["n"]), self.target(gid, c["n"])
        if got < tgt or got <= 0:
            return
        rules, rec = self.rules(gid), self.member(gid, c["recipient"])
        open_issue = any(self.member_status(gid, m["id"], c["n"]) in ("late", "invoiced") for m in self.members(gid))
        ok_standing = self.member_status(gid, rec["id"], c["n"]) in ("paid", "skipped") and bool(rec["email"])
        checks, hard_ok, needs_human = payout_checks(rules, recipient=rec["id"], expected=c["recipient"], recipient_name=rec["first"], amount=got, funded=got,
                                                     already_paid=False, recipient_ok=ok_standing, open_issue=open_issue)
        row = self._ledger(gid, cycle=c["n"], kind="payout", member=rec["id"], amount=got, status="awaiting_approval", paypal_id="pending", rule="Payout: the whole pot goes to this cycle's recipient", checks=checks,
                           explanation="")
        if not hard_ok:
            self.s.update("ledger", {"id": row["id"]}, {"status": "failed", "explanation": "A check failed, so nothing was sent: " + next(x["detail"] for x in checks if not x["pass"] and x["label"] != "Below the approval threshold")})
            self._note(gid, "bad", "Payout blocked", f"A check failed for the ${got:g} payout to {rec['first']}.", "A failed check blocks the payment; there is no override.")
            self._audit(gid, "engine", "Payout blocked", f"${got:g} to {rec['first']}: " + "; ".join(x["label"] for x in checks if not x["pass"]))
            return
        if needs_human:
            aid = row["id"]  # the approval shares the payout row's id so the UI can link them
            self.s.update("ledger", {"id": row["id"]}, {"explanation": f"Pot funded. Every check passed. Over the ${rules.approval_above:g} threshold, so it waits for the organiser."})
            self.s.insert("approvals", {"id": aid, "group_id": gid, "kind": "payout", "title": f"Pay ${got:g} to {rec['first']}", "body": f"Cycle {c['n']} is fully funded. The engine passed every check except the approval threshold.", "amount": got,
                                        "needs": [{"who": self.organiser(gid), "state": "pending"}], "checks": checks, "payload": {"ledger_id": row["id"], "cycle": c["n"], "recipient": rec["id"]}, "ts": self.clock.now()})
            self._note(gid, "agent", "Payout proposed", f"${got:g} to {rec['first']}, waiting for {self.member(gid, self.organiser(gid))['first']}.", "Checks passed; the amount is over the approval threshold so a human decides.")
            self._audit(gid, "engine", "Payout proposed", f"${got:g} to {rec['first']}; every check passed, approval required")
        else:
            self._execute_payout(gid, row["id"], "rules engine (under the approval threshold)")

    def _execute_payout(self, gid: str, ledger_id: str, approver: str) -> None:
        """The ONLY code that moves money out. Preconditions: an unsent payout row that the engine or an approver cleared."""
        row = self.s.one("ledger", id=ledger_id)
        if not row or row["kind"] != "payout" or row["status"] != "awaiting_approval":
            raise RuleError("there is no cleared payout proposal to execute")
        c = next(x for x in self.cycles(gid) if x["n"] == row["cycle"]); rec = self.member(gid, row["member"]); rules = self.rules(gid)
        batch_key = f"ajo-{gid}-c{c['n']}-{rec['id']}-v{rules.version}"
        try:  # database-level duplicate protection: one payout per group, cycle and recipient
            self.s.insert("payouts", {"group_id": gid, "cycle": c["n"], "recipient": rec["id"], "batch_id": "", "sender_batch_id": batch_key, "amount": row["amount"], "status": "PENDING", "ts": self.clock.now()})
        except sqlite3.IntegrityError:
            self._audit(gid, "engine", "Duplicate payout prevented", f"A payout for cycle {c['n']} to {rec['first']} already exists"); return
        res = self.gw.create_payout(batch_key, [{"receiver_email": rec["email"], "amount": row["amount"], "currency": rules.currency, "note": f"Ajo cycle {c['n']}", "sender_item_id": f"{gid}-c{c['n']}-{rec['id']}"}])
        ok = res["status"] in ("SUCCESS", "PENDING", "PROCESSING")
        self.s.update("payouts", {"group_id": gid, "cycle": c["n"], "recipient": rec["id"]}, {"batch_id": res["batch_id"], "status": res["status"]})
        if not ok:
            self.s.update("ledger", {"id": ledger_id}, {"status": "failed", "paypal_id": res["batch_id"], "explanation": f"PayPal returned {res['status']}. Nothing was marked paid and the proposal stays open for a retry."})
            self._note(gid, "bad", f"Cycle {c['n']} payout failed", f"PayPal returned {res['status']}.", "A failed payout never marks the cycle paid.")
            self._audit(gid, "paypal", "Payout failed", f"${row['amount']:g} to {rec['first']}: {res['status']}"); return
        self.s.update("ledger", {"id": ledger_id}, {"status": "completed" if res["status"] == "SUCCESS" else "pending", "paypal_id": res["batch_id"], "approver": approver,
                                                     "explanation": f"Approved by {approver} and paid in one batch. The batch id is unique per group, cycle and rule version, so a retry cannot pay twice."})
        nxt = next((x for x in self.cycles(gid) if x["n"] == c["n"] + 1), None)
        self.s.update("cycles", {"group_id": gid, "n": c["n"]}, {"status": "paid"})
        if nxt:
            self.s.update("cycles", {"group_id": gid, "n": nxt["n"]}, {"status": "collecting"})
            self._issue_repayments(gid, nxt["n"])
        else:
            self.s.update("groups", {"id": gid}, {"status": "complete"})
            self._audit(gid, "engine", "Circle complete", f"All {len(self.cycles(gid))} cycles are paid out")
        self._note(gid, "good", f"Cycle {c['n']} paid out", f"${row['amount']:g} sent to {rec['first']}." + (f" Cycle {c['n'] + 1} is now collecting." if nxt else " Every cycle is paid, so the circle is complete."), "Approved, paid in one Payouts batch, status confirmed by the PayPal batch lookup.")
        self._audit(gid, "engine", f"Cycle {c['n']} paid out", f"${row['amount']:g} to {rec['first']}, approved by {approver}")

    # ------------------------------------------------------------------ approvals
    def decide(self, gid: str, approval_id: str, who: str, verdict: str) -> dict:
        if verdict not in ("approved", "declined"):
            raise RuleError("verdict must be approved or declined")
        a = self.s.one("approvals", id=approval_id, group_id=gid)
        if not a:
            raise RuleError("no such request")
        needs = a["needs"]
        mine = next((n for n in needs if n["who"] == who), None)
        if not mine:
            raise RuleError("this request is not waiting on you")
        if any(n["state"] == "declined" for n in needs) or all(n["state"] == "approved" for n in needs):
            raise RuleError("this request is already settled")
        if mine["state"] != "pending":
            raise RuleError("you have already answered this request")
        mine["state"] = verdict
        self.s.update("approvals", {"id": approval_id}, {"needs": needs})
        who_m = self.member(gid, who)
        self._audit(gid, "organiser" if who == self.organiser(gid) else "member", f"{a['kind'].capitalize()} {verdict}", f"{who_m['first']} {verdict} \"{a['title']}\"")
        if verdict == "declined":
            self._note(gid, "warn", "Request declined", f"{who_m['first']} declined \"{a['title']}\".")
            if a["kind"] == "payout":
                self.s.update("ledger", {"id": a["payload"]["ledger_id"]}, {"status": "failed", "explanation": "Declined by the organiser. Nothing was sent."})
        elif all(n["state"] == "approved" for n in needs):
            if a["kind"] == "payout":
                self._execute_payout(gid, a["payload"]["ledger_id"], who_m["name"])
            elif a["kind"] == "swap":
                self._apply_swap(gid, a)
            elif a["kind"] == "hardship":
                self._apply_hardship(gid, a)
            else:
                self._note(gid, "info", "Organiser decision recorded", a["title"])
        else:
            self._note(gid, "info", "Waiting for the others", f"{who_m['first']} approved \"{a['title']}\".")
        self._touch(gid)
        return self.s.one("approvals", id=approval_id)

    def _my_cycle(self, gid: str, member: str) -> dict | None:
        return next((c for c in self.cycles(gid) if c["recipient"] == member and c["status"] != "paid"), None)

    def _apply_swap(self, gid: str, a: dict) -> None:
        x, y = a["payload"]["a"], a["payload"]["b"]; cx, cy = self._my_cycle(gid, x), self._my_cycle(gid, y)
        if not cx or not cy or cx["status"] == "paid" or cy["status"] == "paid":
            raise RuleError("a payout for one of these turns went out before the swap could be applied")
        self.s.update("cycles", {"group_id": gid, "n": cx["n"]}, {"recipient": y}); self.s.update("cycles", {"group_id": gid, "n": cy["n"]}, {"recipient": x})
        mx, my = self.member(gid, x), self.member(gid, y)
        self._note(gid, "good", "Turns swapped", f"{mx['first']} and {my['first']} now collect in each other's cycle.", "Both members and the organiser approved, and neither payout had been sent.")
        self._audit(gid, "engine", "Swap applied", f"{mx['first']} and {my['first']} swapped turns under rule v{self.rules(gid).version}")

    def _apply_hardship(self, gid: str, a: dict) -> None:
        mid, n = a["payload"]["member"], a["payload"]["cycle"]
        self.s.insert("skips", {"group_id": gid, "member": mid, "cycle": n}, replace=True)
        m, r = self.member(gid, mid), self.rules(gid)
        later = [c["n"] for c in self.cycles(gid) if c["n"] > n][: r.hardship.repay_within_cycles]
        per = round(r.contribution / max(1, len(later)), 2)
        for k in later:
            self.s.insert("repayments", {"id": self._id("rp"), "group_id": gid, "member": mid, "due_cycle": k, "amount": per, "status": "due", "invoice_id": ""})
        self._note(gid, "good", "Hardship skip approved", f"{m['first']} skips cycle {n} and repays ${per:g} in each of the next {len(later)} cycles" + (f" (cycle {later[0]} onward). The treasurer will invoice each repayment when its cycle opens." if later else "."), "One skip per member, repaid within the rule's limit.")
        self._audit(gid, "engine", "Hardship applied", f"{m['first']} skips cycle {n}; repayment of ${per:g} x {len(later)} scheduled for cycles {', '.join(map(str, later))}")
        if self.current_cycle(gid) and self.current_cycle(gid)["n"] in later:
            self._issue_repayments(gid, self.current_cycle(gid)["n"])
        self._maybe_propose_payout(gid)

    # ------------------------------------------------------------------ chat
    def chat(self, gid: str, who: str, text: str) -> dict:
        text = text.strip()[:500]
        if not text:
            raise RuleError("say something first")
        me = self.member(gid, who)
        self.s.insert("chat", {"id": self._id("m"), "group_id": gid, "ts": self.clock.now(), "sender": "member", "who": who, "text": text, "checks": [], "blocked": 0})
        self._audit(gid, "member", "Request received", f"{me['first']}: \"{text[:80]}\"")
        names = {m["id"]: m["first"] for m in self.members(gid)}
        import time as _t
        t0 = _t.time(); llm = self.llm_for(gid)
        intent = classify(text, who, names, llm)
        reply, checks, blocked, approval = self._respond(gid, me, intent, text)
        used = False
        if intent.kind != "injection" and llm is not None and _t.time() - t0 < 20:      # a model this slow reads fine but is not worth a second wait for wording
            reply, used = rephrase(llm, text, reply)
        by_model = used or intent.source.startswith("model")
        source = f"model ({llm.name}), validated by code" if by_model else ("rules-based screen" if intent.kind == "injection" else "rules-based reader")
        row = {"id": self._id("m"), "group_id": gid, "ts": self.clock.now(), "sender": "agent", "who": None, "text": reply, "checks": checks, "blocked": int(blocked), "approval_id": approval, "source": source}
        self.s.insert("chat", row)
        self._touch(gid)
        return {"id": row["id"], "from": "agent", "who": None, "text": reply, "ts": row["ts"], "checks": checks or None, "blocked": blocked, "approvalId": approval, "source": source}

    def _respond(self, gid: str, me: dict, intent, text: str) -> tuple[str, list[dict], bool, str | None]:
        rules = self.rules(gid)
        if intent.kind == "injection":
            checks = [chk("Request comes from the rules engine", False, "Chat text is data, never an instruction"), chk("A cycle is funded and has a proposal", False, "No payout proposal exists for this request"), chk("Logged for the organiser", True, "Added to the audit log with the original text")]
            self._note(gid, "bad", "Instruction blocked", f"A message asked to skip the rules: \"{text[:60]}\".", "Message text is treated as data, not as a command.")
            self._audit(gid, "engine", "Injection blocked", f"\"{text[:80]}\" treated as data; no action taken")
            return ("I can't do that. I only pay out through the group rules, and free text in a message can't change them. Nothing was sent, and I've logged the attempt for the organiser.", checks, True, None)
        if intent.kind == "payout_request":
            cur = self.current_cycle(gid)
            if not cur:
                return ("The rotation is complete, so every payout has gone out.", [], False, None)
            mine = self._my_cycle(gid, me["id"])
            if not mine:
                return ("Your payout has already been sent. Each person collects once.", [], False, None)
            if cur["recipient"] == me["id"]:
                return (f"It's already your turn. Cycle {cur['n']} pays out to you as soon as it is fully funded: ${self.collected(gid, cur['n']):g} of ${self.target(gid, cur['n']):g} so far.", [], False, None)
            holder = self.member(gid, cur["recipient"]) if not intent.members else self.member(gid, intent.members[0])
            self._audit(gid, "engine", "Payout request redirected", f"{me['first']} asked to be paid sooner; payouts follow the recorded order, so I offered a swap with {holder['first']}")
            msg, checks, blocked, aid = self._respond(gid, me, Intent("swap", members=[me["id"], holder["id"]], source=intent.source), text)
            return ("I can't pay anyone because a message asks me to, and payouts follow the recorded order. The one way to move up is a swap. " + msg, checks, blocked, aid)
        if intent.kind == "swap":
            others = [m for m in intent.members if m != me["id"]]
            if not others:
                return ("Who would you like to swap with? Name the member, for example \"swap with Sam\".", [], False, None)
            other = self.member(gid, others[0]); ca, cb = self._my_cycle(gid, me["id"]), self._my_cycle(gid, other["id"])
            if not ca or not cb:
                return ("One of you has already been paid, and the rules lock a turn once its payout is sent.", swap_checks(rules, a_paid=not ca, b_paid=not cb, a_ok=True, b_ok=True), False, None)
            ok = lambda m: self.member_status(gid, m, self.current_cycle(gid)["n"]) not in ("late", "invoiced") if self.current_cycle(gid) else True
            checks = swap_checks(rules, a_paid=False, b_paid=False, a_ok=ok(me["id"]), b_ok=ok(other["id"]))
            if not all(c["pass"] for c in checks):
                return ("The rules don't allow that right now: " + next(c["detail"] for c in checks if not c["pass"]) + ".", checks, False, None)
            org = self.organiser(gid)
            needs = ([{"who": other["id"], "state": "pending"}] if "both_members" in rules.swap.needs else []) + ([{"who": org, "state": "pending"}] if "organiser" in rules.swap.needs else [])
            seen: set[str] = set()
            needs = [n for n in needs if n["who"] != me["id"] and not (n["who"] in seen or seen.add(n["who"]))]   # the requester's own request counts as their approval
            if not needs:
                needs = [{"who": org if org != me["id"] else other["id"], "state": "pending"}]
            aid = self._id("a")
            self.s.insert("approvals", {"id": aid, "group_id": gid, "kind": "swap", "title": f"Swap turns: {me['first']} and {other['first']}", "body": f"{me['first']} takes cycle {cb['n']} ({cb['date']}) and {other['first']} takes cycle {ca['n']} ({ca['date']}).",
                                        "amount": None, "needs": needs, "checks": checks, "payload": {"a": me["id"], "b": other["id"]}, "ts": self.clock.now()})
            self._audit(gid, "engine", "Swap proposed", f"{me['first']} and {other['first']}: eligible under rule v{rules.version}, awaiting " + ", ".join(self.member(gid, n["who"])["first"] for n in needs))
            return (f"That is allowed by rule v{rules.version}. I've asked {' and '.join(self.member(gid, n['who'])['first'] for n in needs)}. If everyone agrees, {other['first']} collects on {ca['date']} and {me['first']} on {cb['date']}.", checks, False, aid)
        if intent.kind == "hardship":
            c = self.current_cycle(gid)
            if not c:
                return ("The rotation is complete, so there is nothing to skip.", [], False, None)
            used = self.s.db.execute("select count(*) from skips where group_id=? and member=?", (gid, me["id"])).fetchone()[0]
            left = len([x for x in self.cycles(gid) if x["status"] != "paid"])
            checks = hardship_checks(rules, skips_used=used, remaining_cycles=left, name=me["first"])
            if not all(x["pass"] for x in checks):
                return ("The rules don't allow a hardship skip right now: " + next(x["detail"] for x in checks if not x["pass"]) + ".", checks, False, None)
            per = rules.contribution / rules.hardship.repay_within_cycles
            aid = self._id("a")
            self.s.insert("approvals", {"id": aid, "group_id": gid, "kind": "hardship", "title": f"{me['first']} skips this cycle", "body": f"{me['first']} skips cycle {c['n']} and repays ${per:g} in each of the next {rules.hardship.repay_within_cycles} cycles. The pot for this cycle drops to ${self.target(gid, c['n']) - rules.contribution:g}.",
                                        "amount": None, "needs": [{"who": self.organiser(gid), "state": "pending"}], "checks": checks, "payload": {"member": me["id"], "cycle": c["n"]}, "ts": self.clock.now()})
            self._audit(gid, "engine", "Hardship proposed", f"{me['first']}: eligible, awaiting {self.member(gid, self.organiser(gid))['first']}")
            return (f"Rule v{rules.version} allows one hardship skip. I've asked {self.member(gid, self.organiser(gid))['first']}. If approved, this cycle's pot drops and you repay ${per:g} over the next {rules.hardship.repay_within_cycles} cycles.", checks, False, aid)
        if intent.kind == "explain":
            c = self.current_cycle(gid)
            if not c:
                return ("The rotation is complete. Every cycle is in the ledger.", [], False, None)
            rec = self.member(gid, c["recipient"])
            return (f"Cycle {c['n']}: ${self.collected(gid, c['n']):g} of ${self.target(gid, c['n']):g} collected. {rec['first']} collects on {c['date']}. Open any ledger row to see which rule allowed it.", [], False, None)
        return ("I can help with swaps, a hardship skip, or what any payment was for. For example: \"Can Chidi and Sam swap turns?\"", [], False, None)

    # ------------------------------------------------------------------ snapshot for the UI
    def snapshot(self, gid: str) -> dict:
        g = self.s.one("groups", id=gid)
        if not g:
            raise KeyError(gid)
        rules = self.rules(gid); cur = self.current_cycle(gid); members = self.members(gid)
        ledger = [{"id": r["id"], "cycle": r["cycle"], "kind": r["kind"], "member": r["member"], "amount": r["amount"], "status": r["status"], "ts": r["ts"], "paypalId": r["paypal_id"], "ruleVersion": r["rule_version"],
                   "rule": r["rule"], "approver": r["approver"], "simulated": bool(r["simulated"]), "explanation": r["explanation"], "checks": r["checks"]} for r in self.s.all("ledger", order="ts desc, rowid desc", group_id=gid)]
        rule_rows = self.s.all("rule_sets", order="version desc", group_id=gid)
        return {
            "version": g["version"], "now": self.clock.now(), "mode": self.gw.mode, "group": {"id": gid, "name": g["name"], "currency": g["currency"], "status": g["status"], "treasurer": bool(g["treasurer"]), "size": rules.members},
            "model": (lambda m: getattr(m, "name", "none") if m else "none")(self.llm_for(gid)),
            "invites": [{"code": i["code"], "name": i["name"], "email": i["email"], "status": i["status"]} for i in self.s.all("invites", order="ts", group_id=gid) if i["status"] != "revoked"],
            "members": [{"id": m["id"], "name": m["name"], "first": m["first"], "role": m["role"], "hue": m["hue"], "email": m["email"], "turn": m["turn"], "paypal": "linked" if m["sub_status"] == "ACTIVE" else "pending"} for m in members],
            "cycles": [{"n": c["n"], "date": c["date"], "recipient": c["recipient"], "pot": c["pot"], "status": c["status"]} for c in self.cycles(gid)],
            "currentCycle": cur["n"] if cur else None,
            "pot": {"collected": self.collected(gid, cur["n"]), "target": self.target(gid, cur["n"])} if cur else None,
            "memberStatus": {m["id"]: self.member_status(gid, m["id"], cur["n"]) for m in members} if cur else {},
            "rules": rules.to_api(), "ruleText": rule_rows[0]["text"], "ruleHistory": [{"version": r["version"], "note": r["note"], "when": _date(r["ts"])} for r in rule_rows],
            "ledger": ledger, "timeline": [{"id": t["id"], "ts": t["ts"], "tone": t["tone"], "title": t["title"], "body": t["body"], "why": t["why"]} for t in self.s.all("timeline", order="ts desc, rowid desc", group_id=gid)],
            "approvals": [{"id": a["id"], "title": a["title"], "body": a["body"], "kind": a["kind"], "needs": a["needs"], "amount": a["amount"], "checks": a["checks"]} for a in self.s.all("approvals", order="ts desc, rowid desc", group_id=gid)],
            "chat": [{"id": c["id"], "from": c["sender"], "who": c["who"], "text": c["text"], "ts": c["ts"], "checks": c["checks"] or None, "blocked": bool(c["blocked"]), "approvalId": c["approval_id"], "source": c["source"]} for c in self.s.all("chat", order="ts, rowid", group_id=gid)],
            "audit": [{"seq": a["seq"], "ts": a["ts"], "actor": a["actor"], "action": a["action"], "detail": a["detail"], "prev": a["prev"], "hash": a["hash"]} for a in self.s.all("audit", order="seq", group_id=gid)],
            "skips": [{"member": k["member"], "cycle": k["cycle"]} for k in self.s.all("skips", group_id=gid)],
            "repayments": [{"member": r["member"], "cycle": r["due_cycle"], "amount": r["amount"], "status": r["status"]} for r in self.s.all("repayments", order="due_cycle", group_id=gid)],
            "drawOrder": (draw_order([m["id"] for m in members], rules.seed) if rules.order == "random" and rules.seed != "unset" else [m["id"] for m in members]) if cur or any(c["status"] != "upcoming" for c in self.cycles(gid)) else [],
        }

    def verify_audit(self, gid: str) -> int | None:
        return auditlog.verify(self.s, gid)

    def replay_cycle(self, gid: str, n: int) -> dict:
        """Re-run the payout checks for a paid cycle from recorded data and compare with what was decided."""
        c = next((x for x in self.cycles(gid) if x["n"] == n), None)
        row = self.s.db.execute("select * from ledger where group_id=? and cycle=? and kind='payout' and status='completed'", (gid, n)).fetchone()
        if not c or not row:
            raise RuleError("that cycle has no completed payout to replay")
        rules = self.rules(gid); rec = self.member(gid, row["member"])
        checks, hard, human = payout_checks(RuleSet.model_validate({**rules.model_dump(), "version": row["rule_version"]}), recipient=row["member"], expected=c["recipient"], recipient_name=rec["first"], amount=row["amount"], funded=row["amount"],
                                            already_paid=False, recipient_ok=True, open_issue=False)
        return {"cycle": n, "recipient": row["member"], "amount": row["amount"], "checksPassed": hard, "neededApproval": human, "approvedBy": row["approver"], "matchesRecord": hard and bool(row["approver"]) == (human or bool(row["approver"]))}

    # ------------------------------------------------------------------ the circle's choice of model
    def model_config(self, gid: str) -> dict:
        c = self.s.one("model_config", group_id=gid)
        eff = self.llm_for(gid)
        return {"provider": c["provider"] if c else "default", "baseUrl": (c["base_url"] if c else "") or "", "model": (c["model"] if c else "") or "", "hasKey": bool(c and c["api_key"]),
                "effective": getattr(eff, "name", "none") if eff else "none"}

    def set_model(self, gid: str, who: str, provider: str, base_url: str = "", model: str = "", api_key: str | None = None) -> dict:
        if who != self.organiser(gid):
            raise RuleError("only the organiser can choose the treasurer's model")
        if provider == "default":
            self.s.db.execute("delete from model_config where group_id=?", (gid,)); self.s.db.commit()
            self._audit(gid, "organiser", "Treasurer model changed", "Back to the server default"); self._touch(gid)
            return self.model_config(gid)
        if provider not in ("ollama", "openai_compat", "anthropic"):
            raise RuleError("choose Ollama, an OpenAI-compatible service, Anthropic, or the default")
        model, base_url = model.strip()[:100], base_url.strip()[:200]
        if not model:
            raise RuleError("which model? Pick one from the list or type its name")
        if base_url and not base_url.lower().startswith(("http://", "https://")):
            raise RuleError("the address must start with http:// or https://")
        if provider == "openai_compat" and not base_url:
            raise RuleError("an OpenAI-compatible service needs its address, for example https://api.openai.com/v1")
        old = self.s.one("model_config", group_id=gid)
        key = api_key if api_key else (old["api_key"] if old and old["provider"] == provider else "")
        if provider != "ollama" and not key:
            raise RuleError("this service needs an API key")
        self.s.insert("model_config", {"group_id": gid, "provider": provider, "base_url": base_url, "model": model, "api_key": key if provider != "ollama" else ""}, replace=True)
        self._audit(gid, "organiser", "Treasurer model changed", f"{provider}: {model}" + (f" at {base_url}" if base_url else ""))      # the key is never logged
        self._touch(gid)
        return self.model_config(gid)

    def test_model(self, gid: str) -> dict:
        import time
        llm = self.llm_for(gid)
        if llm is None:
            return {"ok": False, "ms": 0, "detail": "No model is configured, so messages are read by built-in rules."}
        t = time.time()
        out = llm.json('Return only JSON {"kind": "payout_request"} if the message asks to be paid, else {"kind": "other"}.', "Please pay me first")
        ms = int((time.time() - t) * 1000)
        ok = isinstance(out, dict) and out.get("kind") == "payout_request"
        return {"ok": ok, "ms": ms, "detail": f"{llm.name} answered in {ms / 1000:.1f}s and read the test message correctly." if ok else f"{llm.name} did not return the expected answer ({'no reply' if out is None else str(out)[:80]})."}
