from __future__ import annotations

from typing import Protocol

from ..config import Settings


class Gateway(Protocol):
    """Everything the engine needs from PayPal. Two implementations: the real sandbox client and an in-memory simulator."""
    mode: str
    def create_plan(self, name: str, amount: float, currency: str, interval_days: int) -> str: ...
    def create_subscription(self, plan_id: str, email: str, name: str) -> dict: ...
    def create_payout(self, sender_batch_id: str, items: list[dict]) -> dict: ...
    def get_payout(self, batch_id: str) -> dict: ...
    def create_invoice(self, email: str, amount: float, currency: str, note: str, number: str) -> dict: ...
    def send_invoice(self, invoice_id: str) -> None: ...
    def remind_invoice(self, invoice_id: str, note: str) -> None: ...
    def verify_webhook(self, headers: dict[str, str], raw: bytes) -> bool: ...


def make_gateway(s: Settings) -> Gateway:
    if s.paypal_mode == "sandbox":
        if not (s.paypal_client_id and s.paypal_client_secret):
            raise RuntimeError("PAYPAL_MODE=sandbox needs PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET")
        from .real import RealGateway
        return RealGateway(s)
    from .fake import FakeGateway
    return FakeGateway(s.fake_webhook_secret)
