import json

from .engine import Engine, RuleError
from .paypal.base import Gateway


class BadSignature(Exception):
    pass


def ingest(engine: Engine, gateway: Gateway, raw: bytes, headers: dict[str, str]) -> dict:
    """The one door for PayPal events: verify the signature first, then hand the parsed event to the engine."""
    if not gateway.verify_webhook(headers, raw):
        raise BadSignature("webhook signature did not verify")
    try:
        event = json.loads(raw)
    except ValueError as e:
        raise RuleError("webhook body is not JSON") from e
    return engine.handle_event(event)
