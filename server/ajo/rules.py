"""The deterministic half: rule sets, validation, and every check that guards money. Nothing in here calls a model or PayPal."""
from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, Field, field_validator

LadderAction = Literal["invoice_and_remind", "warn_group", "organiser_decision"]
LADDER_TEXT: dict[str, str] = {"invoice_and_remind": "Invoice and remind", "warn_group": "Warn the group", "organiser_decision": "Organiser decides"}


class LadderStep(BaseModel):
    after: int = Field(ge=1, le=10)
    action: LadderAction


class SwapRule(BaseModel):
    allowed: bool = True
    needs: list[Literal["both_members", "organiser"]] = ["both_members", "organiser"]
    locked_after_payout: bool = True


class HardshipRule(BaseModel):
    allowed: bool = True
    max_skips_per_member: int = Field(1, ge=0, le=5)
    repay_within_cycles: int = Field(2, ge=1, le=12)


class RuleSet(BaseModel):
    version: int = 1
    currency: str = "USD"
    contribution: float = Field(50, gt=0, le=100000)
    cycle_days: int = Field(14, ge=1, le=92)
    members: int = Field(5, ge=2, le=50)
    order: Literal["random", "fixed"] = "random"
    seed: str = "unset"
    grace_days: int = Field(2, ge=0, le=14)
    ladder: list[LadderStep] = [LadderStep(after=1, action="invoice_and_remind"), LadderStep(after=2, action="warn_group"), LadderStep(after=3, action="organiser_decision")]
    swap: SwapRule = SwapRule()
    hardship: HardshipRule = HardshipRule()
    max_payout: float = Field(300, gt=0)
    approval_above: float = Field(200, ge=0)

    @field_validator("currency")
    @classmethod
    def _cur(cls, v: str) -> str:
        v = v.upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError("currency must be a three-letter code")
        return v

    @property
    def pot(self) -> float:
        return round(self.contribution * self.members, 2)

    def to_api(self) -> dict:
        sw = "Both members and the organiser must agree." if self.swap.allowed else "Swaps are not allowed."
        if self.swap.allowed and self.swap.locked_after_payout:
            sw += " Locked once a payout is sent."
        hs = (f"{self.hardship.max_skips_per_member} skipped cycle per member, repaid within {self.hardship.repay_within_cycles} cycles." if self.hardship.allowed else "Hardship skips are not allowed.")
        return {"version": self.version, "currency": self.currency, "contribution": self.contribution, "cycleDays": self.cycle_days, "members": self.members, "order": self.order,
                "seed": self.seed, "graceDays": self.grace_days, "ladder": [{"after": s.after, "action": LADDER_TEXT[s.action]} for s in self.ladder], "swap": sw, "hardship": hs,
                "maxPayout": self.max_payout, "approvalAbove": self.approval_above}


def validate_rules(r: RuleSet) -> list[str]:
    """Conflicts the organiser must resolve before a rule set can go live. Returns plain-language problems."""
    problems: list[str] = []
    if r.pot > r.max_payout:
        problems.append(f"The pot is {r.pot:g} but the maximum single payout is {r.max_payout:g}, so no cycle could ever be paid out.")
    if r.hardship.allowed and r.pot <= r.max_payout < r.pot + r.contribution / r.hardship.repay_within_cycles:
        problems.append(f"Hardship repayments are paid into the pot, so a cycle can hold up to {r.pot + r.contribution / r.hardship.repay_within_cycles:g}, but the maximum single payout is {r.max_payout:g}. "
                        "That cycle could never be paid out. Raise the maximum payout or turn hardship skips off.")
    if r.approval_above > r.max_payout:
        problems.append("The approval threshold is above the maximum payout, so it would never apply.")
    steps = [s.after for s in r.ladder]
    if steps != sorted(set(steps)):
        problems.append("The late-payment ladder steps must be in increasing order with no repeats.")
    if r.hardship.allowed and r.hardship.repay_within_cycles >= r.members:
        problems.append("A hardship skip must be repaid before the rotation ends; repay_within_cycles is too long for this group size.")
    if r.hardship.allowed and r.hardship.max_skips_per_member * 1 > r.members - 1:
        problems.append("Hardship skips could leave a pot with fewer than two contributors.")
    return problems


def draw_order(member_ids: list[str], seed: str) -> list[str]:
    """Reproducible random draw: the same seed and members always give the same order."""
    ids = sorted(member_ids)
    random.Random(seed).shuffle(ids)
    return ids


# ---------- checks ----------
def chk(label: str, ok: bool, detail: str) -> dict:
    return {"label": label, "pass": bool(ok), "detail": detail}


def contribution_checks(rules: RuleSet, amount: float, payer_known: bool, duplicate: bool, cycle: int) -> list[dict]:
    return [
        chk("Amount matches the contribution rule", abs(amount - rules.contribution) < 0.005, f"${rules.contribution:.2f} expected, ${amount:.2f} received"),
        chk("Payer is a group member", payer_known, "Matched by subscription id" if payer_known else "No member has this subscription id"),
        chk("Not a duplicate event", not duplicate, f"Webhook id first seen for cycle {cycle}" if not duplicate else "This event id was already processed"),
    ]


def payout_checks(rules: RuleSet, *, recipient: str, expected: str, recipient_name: str, amount: float, funded: float, already_paid: bool, recipient_ok: bool,
                  open_issue: bool, source: str = "engine") -> tuple[list[dict], bool, bool]:
    """Returns (checks, all_hard_checks_pass, needs_human). Hard checks block; the threshold only routes to a human."""
    hard = [
        chk("Recipient is correct for this cycle", recipient == expected, f"{recipient_name} holds this turn under rule v{rules.version}" if recipient == expected else f"Turn belongs to {expected}, not {recipient}"),
        chk("Amount equals the funded pot", abs(amount - funded) < 0.005, f"${funded:g} collected, ${amount:g} to pay"),
        chk("No earlier payout for this cycle", not already_paid, "Unique per group, cycle and recipient" if not already_paid else "A payout for this cycle already exists"),
        chk("Recipient is in good standing", recipient_ok, "Verified PayPal address, no open late flag" if recipient_ok else "Recipient has an open late flag or no verified address"),
        chk("No unresolved failed payment or dispute", not open_issue, "Nothing outstanding in this group" if not open_issue else "A failed payment is still open"),
        chk("Within the maximum single payout", amount <= rules.max_payout, f"${amount:g} is {'under' if amount <= rules.max_payout else 'over'} the ${rules.max_payout:g} limit"),
        chk("Proposal came from the rules engine", source == "engine", "Not derived from chat text" if source == "engine" else "Proposals from free text are never accepted"),
    ]
    needs_human = amount > rules.approval_above
    threshold = chk("Below the approval threshold", not needs_human, f"${amount:g} is {'under' if not needs_human else 'above'} ${rules.approval_above:g}" + ("" if not needs_human else ", so the organiser must approve"))
    return hard + [threshold], all(c["pass"] for c in hard), needs_human


def swap_checks(rules: RuleSet, *, a_paid: bool, b_paid: bool, a_ok: bool, b_ok: bool) -> list[dict]:
    return [
        chk("Swaps are allowed by the rules", rules.swap.allowed, "Rule v%d: both members and the organiser agree" % rules.version if rules.swap.allowed else "Swaps are turned off"),
        chk("Neither payout has gone out", not (rules.swap.locked_after_payout and (a_paid or b_paid)), "Both cycles are still upcoming" if not (a_paid or b_paid) else "A payout for one of these turns was already sent"),
        chk("Both members are in good standing", a_ok and b_ok, "No late flags" if a_ok and b_ok else "One of the members has an open late flag"),
    ]


def hardship_checks(rules: RuleSet, *, skips_used: int, remaining_cycles: int, name: str) -> list[dict]:
    return [
        chk("Hardship is allowed by the rules", rules.hardship.allowed, f"{rules.hardship.max_skips_per_member} skipped cycle per member" if rules.hardship.allowed else "Hardship skips are turned off"),
        chk("No earlier skip used", skips_used < rules.hardship.max_skips_per_member, f"{name} has used {skips_used} of {rules.hardship.max_skips_per_member}"),
        chk("Repayment fits the rule", remaining_cycles - 1 >= 1 and rules.hardship.repay_within_cycles >= 1, f"Repaid over the next {min(rules.hardship.repay_within_cycles, max(remaining_cycles - 1, 1))} cycles"),
    ]
