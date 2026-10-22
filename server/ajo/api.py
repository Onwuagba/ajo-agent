"""HTTP surface for the front end and for PayPal's webhooks.
Every group route needs a signed-in member of that group. The acting member always comes from the session, never from the request body."""
from __future__ import annotations

import asyncio
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from . import accounts
from .ai.llm import LLM, list_ollama, make_llm
from .clock import Clock
from .config import Settings
from .engine import Engine, RuleError
from .paypal.base import Gateway, make_gateway
from .paypal.fake import FakeGateway
from .rules import RuleSet
from .sandbox import Sandbox
from .store import Store
from .webhooks import BadSignature, ingest


class RegisterIn(BaseModel):
    name: str = Field(max_length=80)
    email: str = Field(max_length=160)
    password: str = Field(max_length=200)


class LoginIn(BaseModel):
    email: str = Field(max_length=160)
    password: str = Field(max_length=200)


class NewGroupIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    size: int = Field(ge=2, le=50)
    contribution: float = Field(gt=0, le=100000)
    cycleDays: int = Field(ge=1, le=92)
    currency: str = "USD"


class InviteIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    email: str = Field("", max_length=120)


class ParseIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)


class ConfirmIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)
    raw: dict


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class DecideIn(BaseModel):
    verdict: str


class ModelIn(BaseModel):
    provider: str
    baseUrl: str = Field("", max_length=200)
    model: str = Field("", max_length=100)
    apiKey: str | None = Field(None, max_length=300)


class MemberIn(BaseModel):
    member: str


class AdvanceIn(BaseModel):
    days: float


def create_app(settings: Settings | None = None, gateway: Gateway | None = None, clock: Clock | None = None, llm: LLM | None = None) -> FastAPI:
    st = settings or Settings.from_env()
    gw = gateway or make_gateway(st)
    clk = clock or Clock()
    engine = Engine(Store(st.db_path), gw, clk, llm if llm is not None else make_llm(st), st)
    sandbox = Sandbox(engine, gw) if isinstance(gw, FakeGateway) else None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async def ticker():          # time-based rules (grace periods, reminders) run without anyone opening the app
            while True:
                await asyncio.sleep(30)
                for g in engine.s.all("groups", status="active"):
                    try:
                        engine.tick(g["id"])
                    except Exception:   # one broken group must not stop the others
                        pass
        task = asyncio.create_task(ticker())
        yield
        task.cancel()

    app = FastAPI(title="Ajo treasurer API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=st.cors_origins, allow_methods=["*"], allow_headers=["*"])
    app.state.engine, app.state.gateway, app.state.sandbox, app.state.settings = engine, gw, sandbox, st

    @app.exception_handler(RuleError)
    async def _rule_error(_: Request, e: RuleError):
        return JSONResponse({"error": str(e)}, status_code=422)

    @app.exception_handler(accounts.AuthError)
    async def _auth_error(_: Request, e: accounts.AuthError):
        return JSONResponse({"error": str(e)}, status_code=422)

    @app.exception_handler(KeyError)
    async def _missing(_: Request, e: KeyError):
        return JSONResponse({"error": "not found"}, status_code=404)

    # ---------------------------------------------------------------- identity
    def token_of(request: Request) -> str | None:
        h = request.headers.get("authorization", "")
        return h[7:] if h.lower().startswith("bearer ") else None

    def me(request: Request) -> dict:
        u = accounts.user_for(engine.s, token_of(request))
        if not u:
            raise HTTPException(401, "sign in first")
        return u

    def member_of(gid: str, request: Request, user: dict = Depends(me)) -> str:
        """The member id this request acts as. The simulator lets the organiser act as a sandbox friend, so one person can show a whole group."""
        if not engine.s.one("groups", id=gid):
            raise HTTPException(404, "not found")
        if not engine.s.one("members", group_id=gid, id=user["id"]):
            raise HTTPException(403, "you are not in this group")
        act = request.headers.get("x-act-as")
        if act and act != user["id"]:
            target = engine.s.one("users", id=act)
            if sandbox is None or not target or not target["sandbox"] or not engine.s.one("members", group_id=gid, id=act):
                raise HTTPException(403, "you cannot act as that member")
            return act
        return user["id"]

    def need_sandbox() -> Sandbox:
        if sandbox is None:
            raise HTTPException(404, "the simulator needs PAYPAL_MODE=fake")
        return sandbox

    @app.get("/api/health")
    def health():
        return {"ok": True, "paypal": gw.mode, "llm": getattr(engine.llm, "name", "none") if engine.llm else "none", "sandbox": sandbox is not None}

    @app.post("/api/auth/register")
    def register(body: RegisterIn):
        u = accounts.register(engine.s, body.name, body.email, body.password, clk.now())
        return {"token": accounts.start_session(engine.s, u["id"], clk.now()), "user": accounts.public(u)}

    @app.post("/api/auth/login")
    def login(body: LoginIn):
        u = accounts.login(engine.s, body.email, body.password)
        return {"token": accounts.start_session(engine.s, u["id"], clk.now()), "user": accounts.public(u)}

    @app.get("/api/auth/me")
    def whoami(user: dict = Depends(me)):
        return {"user": accounts.public(user)}

    @app.post("/api/auth/logout")
    def logout(request: Request, user: dict = Depends(me)):
        accounts.end_session(engine.s, token_of(request) or "")
        return {"ok": True}

    # ---------------------------------------------------------------- groups
    @app.get("/api/me/groups")
    def my_groups(user: dict = Depends(me)):
        rows = engine.s.db.execute("select g.id, g.name, g.status, m.role from members m join groups g on g.id = m.group_id where m.id=? order by g.created_ts desc", (user["id"],)).fetchall()
        return [{"id": r["id"], "name": r["name"], "status": r["status"], "role": r["role"], "members": len(engine.members(r["id"])), "size": engine.rules(r["id"]).members} for r in rows]

    @app.post("/api/groups")
    def new_group(body: NewGroupIn, user: dict = Depends(me)):
        gid = (re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:30] or "group") + "-" + uuid.uuid4().hex[:4]
        engine.open_group(gid, body.name, user, body.size, body.contribution, body.cycleDays, body.currency)
        return {"id": gid}

    @app.get("/api/groups/{gid}/state")
    def state(gid: str, who: str = Depends(member_of)):
        snap = engine.snapshot(gid)
        snap["you"] = who
        flags = {r["id"]: bool(r["sandbox"]) for r in engine.s.db.execute("select id, sandbox from users")}
        for m in snap["members"]:
            m["sandbox"] = flags.get(m["id"], False)
        if who != engine.organiser(gid):
            for m in snap["members"]:
                if m["id"] != who:
                    m["email"] = ""     # contact details are the organiser's to see
        mine = engine.s.one("members", group_id=gid, id=who)
        snap["payment"] = {"status": "linked" if mine["sub_status"] == "ACTIVE" else "pending", "approveUrl": mine["approve_url"] or "", "simulated": sandbox is not None}
        if who != engine.organiser(gid):
            snap["invites"] = []        # invite links are capabilities; only the organiser sees them
        return snap

    @app.post("/api/groups/{gid}/invites")
    def invite(gid: str, body: InviteIn, who: str = Depends(member_of)):
        return engine.invite(gid, who, body.name, body.email)

    @app.delete("/api/groups/{gid}/invites/{code}")
    def revoke(gid: str, code: str, who: str = Depends(member_of)):
        engine.revoke_invite(gid, who, code)
        return {"ok": True}

    @app.delete("/api/groups/{gid}/members/{mid}")
    def remove_member(gid: str, mid: str, who: str = Depends(member_of)):
        engine.remove_member(gid, who, mid)
        return {"ok": True}

    @app.get("/api/invites/{code}")
    def invite_info(code: str):
        return engine.invite_info(code)

    @app.post("/api/invites/{code}/accept")
    def accept(code: str, user: dict = Depends(me)):
        return {"group": engine.accept_invite(code, user)}

    @app.post("/api/groups/{gid}/rules/parse")
    def parse(gid: str, body: ParseIn, who: str = Depends(member_of)):
        r = engine.parse_rules(gid, body.text)
        return {"rules": r.rules.to_api(), "raw": r.rules.model_dump(), "questions": r.questions, "problems": r.problems, "source": r.source}

    def _rules(raw: dict) -> RuleSet:
        try:
            return RuleSet.model_validate(raw)
        except ValidationError as e:
            raise RuleError("those rules are not valid: " + "; ".join(x["msg"] for x in e.errors())[:300])

    @app.post("/api/groups/{gid}/rules/confirm")
    def confirm(gid: str, body: ConfirmIn, who: str = Depends(member_of)):
        return engine.confirm_rules(gid, who, body.text, _rules(body.raw)).to_api()

    @app.post("/api/groups/{gid}/treasurer")
    def appoint(gid: str, body: ConfirmIn, who: str = Depends(member_of)):
        return engine.appoint_treasurer(gid, who, body.text, _rules(body.raw)).to_api()

    @app.post("/api/groups/{gid}/activate")
    def activate(gid: str, who: str = Depends(member_of)):
        engine.activate(gid, who)
        return {"ok": True}

    @app.post("/api/groups/{gid}/subscription/approve")
    def approve_subscription(gid: str, who: str = Depends(member_of)):
        """Simulator only: stands in for the member approving their subscription on PayPal's own page. With real PayPal the member follows approveUrl and PayPal's webhook does the rest."""
        return need_sandbox().approve_subscription(gid, who)

    @app.get("/api/groups/{gid}/model")
    def get_model(gid: str, who: str = Depends(member_of)):
        return {**engine.model_config(gid), "installed": list_ollama(st.ollama_url), "ollamaUrl": st.ollama_url}

    @app.put("/api/groups/{gid}/model")
    def put_model(gid: str, body: ModelIn, who: str = Depends(member_of)):
        return engine.set_model(gid, who, body.provider, body.baseUrl, body.model, body.apiKey)

    @app.post("/api/groups/{gid}/model/test")
    def test_model(gid: str, who: str = Depends(member_of)):
        return engine.test_model(gid)

    @app.post("/api/groups/{gid}/chat")
    def chat(gid: str, body: ChatIn, who: str = Depends(member_of)):
        return engine.chat(gid, who, body.text)

    @app.post("/api/groups/{gid}/approvals/{aid}/decide")
    def decide(gid: str, aid: str, body: DecideIn, who: str = Depends(member_of)):
        return engine.decide(gid, aid, who, body.verdict)

    @app.post("/api/groups/{gid}/tick")
    def tick(gid: str, who: str = Depends(member_of)):
        return {"actions": engine.tick(gid)}

    @app.get("/api/groups/{gid}/audit/verify")
    def verify(gid: str, who: str = Depends(member_of)):
        bad = engine.verify_audit(gid)
        return {"intact": bad is None, "brokenAt": bad}

    @app.get("/api/groups/{gid}/audit/replay/{n}")
    def replay(gid: str, n: int, who: str = Depends(member_of)):
        return engine.replay_cycle(gid, n)

    @app.post("/api/webhooks/paypal")
    async def webhook(request: Request):
        raw = await request.body()
        try:
            return ingest(engine, gw, raw, dict(request.headers))
        except BadSignature:
            raise HTTPException(400, "invalid webhook signature")

    # ---------------------------------------------------------------- simulator (PayPal and time stand-ins; PAYPAL_MODE=fake only)
    @app.post("/api/sandbox/{gid}/join-friends")
    def sim_join(gid: str, who: str = Depends(member_of)):
        return {"members": need_sandbox().join_friends(gid)}

    @app.post("/api/sandbox/{gid}/approve-friends")
    def sim_approve(gid: str, who: str = Depends(member_of)):
        return {"approved": need_sandbox().approve_friends(gid)}

    @app.post("/api/sandbox/{gid}/pay")
    def sim_pay(gid: str, body: MemberIn, who: str = Depends(member_of)):
        return need_sandbox().pay(gid, body.member)

    @app.post("/api/sandbox/{gid}/fail")
    def sim_fail(gid: str, body: MemberIn, who: str = Depends(member_of)):
        return need_sandbox().fail(gid, body.member)

    @app.post("/api/sandbox/{gid}/pay-invoice")
    def sim_invoice(gid: str, body: MemberIn, who: str = Depends(member_of)):
        return need_sandbox().pay_invoice(gid, body.member)

    @app.post("/api/sandbox/{gid}/advance")
    def sim_advance(gid: str, body: AdvanceIn, who: str = Depends(member_of)):
        return {"actions": need_sandbox().advance(gid, body.days)}

    @app.post("/api/sandbox/{gid}/tamper/{seq}")
    def sim_tamper(gid: str, seq: int, undo: bool = False, who: str = Depends(member_of)):
        need_sandbox().tamper(gid, seq, undo)
        return {"seq": seq, "edited": not undo}

    return app


def app_factory() -> FastAPI:  # `uvicorn ajo.api:app_factory --factory`
    return create_app()
