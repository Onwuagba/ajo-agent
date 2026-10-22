import pytest

from ajo.clock import Clock
from ajo.demo import GID, Demo
from ajo.engine import Engine
from ajo.paypal.fake import FakeGateway
from ajo.store import Store


@pytest.fixture
def env():
    gw, clk = FakeGateway(), Clock(1_760_000_000_000)
    eng = Engine(Store(":memory:"), gw, clk)
    demo = Demo(eng, gw)
    demo.seed()
    return eng, gw, clk, demo


def sub(eng, mid):
    return eng.member(GID, mid)["subscription_id"]


def pending(eng, kind):
    return [a for a in eng.snapshot(GID)["approvals"] if a["kind"] == kind and any(n["state"] == "pending" for n in a["needs"])]
