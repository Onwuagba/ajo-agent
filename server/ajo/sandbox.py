"""The sandbox simulator: stands in for the parts of the world a single person cannot do alone in a demo (friends accepting invites, PayPal
payments arriving, time passing). Every action goes through the same engine and the same signed-webhook path a real PayPal event would use.
Only available with the PayPal simulator (PAYPAL_MODE=fake); the front end labels everything it produces as simulated."""
from __future__ import annotations

from . import accounts
from .engine import Engine, RuleError
from .paypal.fake import FakeGateway
from .webhooks import ingest

FRIENDS = ["Tunde Adeyemi", "Fatima Bello", "Chidi Nwosu", "Sam Kamau", "Ngozi Eze", "Kofi Mensah", "Zainab Musa"]


class Sandbox:
    def __init__(self, engine: Engine, gateway: FakeGateway):
        self.e, self.gw = engine, gateway

    def _deliver(self, ev: tuple[bytes, dict[str, str]]) -> dict:
        return ingest(self.e, self.gw, *ev)

    def _sub(self, gid: str, mid: str) -> str:
        sub = self.e.member(gid, mid)["subscription_id"]
        if not sub:
            raise RuleError("the group has not started yet, so there is no PayPal subscription to charge")
        return sub

    def join_friends(self, gid: str) -> list[str]:
        """Pending invitees accept, as sandbox accounts, and the rest of the places fill from a list of friends."""
        e = self.e
        if e.status(gid) != "forming":
            raise RuleError("this group is already running")
        size, joined = e.rules(gid).members, [m["name"] for m in e.members(gid)]
        for inv in [i for i in e.s.all("invites", order="ts", group_id=gid) if i["status"] == "pending"]:
            if len(e.members(gid)) >= size:
                break
            email = inv["email"] or f"{inv['name'].split()[0].lower()}.{inv['code'][:4]}@sandbox.example"
            u = e.s.one("users", email=email) or accounts.register(e.s, inv["name"], email, "sandbox-" + inv["code"], e.clock.now(), sandbox=True)
            e.accept_invite(inv["code"], u)
        pool = [n for n in FRIENDS if n not in joined]
        while len(e.members(gid)) < size and pool:
            name = pool.pop(0)
            inv = e.invite(gid, e.organiser(gid), name)
            u = accounts.register(e.s, name, f"{name.split()[0].lower()}.{inv['code'][:4]}@sandbox.example", "sandbox-" + inv["code"], e.clock.now(), sandbox=True)
            e.accept_invite(inv["code"], u)
        return [m["name"] for m in e.members(gid)]

    def approve_subscription(self, gid: str, mid: str) -> dict:
        """The member approves their subscription at PayPal (simulated)."""
        return self._deliver(self.gw.subscription_activated(self._sub(gid, mid)))

    def approve_friends(self, gid: str) -> int:
        n = 0
        for m in self.e.members(gid):
            u = self.e.s.one("users", id=m["id"])
            if u and u["sandbox"] and m["sub_status"] != "ACTIVE":
                self.approve_subscription(gid, m["id"]); n += 1
        return n

    def pay(self, gid: str, mid: str) -> dict:
        return self._deliver(self.gw.payment_completed(self._sub(gid, mid), self.e.rules(gid).contribution))

    def fail(self, gid: str, mid: str) -> dict:
        return self._deliver(self.gw.payment_failed(self._sub(gid, mid)))

    def pay_invoice(self, gid: str, mid: str) -> dict:
        row = self.e.s.db.execute("select id from invoices where group_id=? and member=? and status!='PAID' order by ts desc", (gid, mid)).fetchone()
        if not row:
            raise RuleError("this member has no open invoice")
        return self._deliver(self.gw.invoice_paid(row["id"], self.e.rules(gid).contribution))

    def advance(self, gid: str, days: float) -> list[str]:
        if not 0 < days <= 92:
            raise RuleError("move time forward by between 0 and 92 days")
        self.e.clock.advance(days=days)
        return self.e.tick(gid)

    def tamper(self, gid: str, seq: int, undo: bool = False) -> None:
        row = self.e.s.one("audit", group_id=gid, seq=seq)
        if not row:
            raise KeyError(seq)
        d = row["detail"].replace(" (edited)", "") if undo else row["detail"] + " (edited)"
        self.e.s.update("audit", {"group_id": gid, "seq": seq}, {"detail": d})
