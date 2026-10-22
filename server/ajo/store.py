"""A deliberately small SQLite layer. Tables hold what needs constraints (idempotency) as columns and the rest as JSON."""
import json
import sqlite3
import threading
from typing import Any

SCHEMA = """
create table if not exists groups (id text primary key, name text, currency text, plan_id text, created_ts integer, version integer default 0, status text default 'active', treasurer integer default 1, owner text);
create table if not exists members (id text, group_id text, name text, first text, role text, hue integer, email text, turn integer, subscription_id text, sub_status text default 'ACTIVE', approve_url text, primary key (group_id, id));
create table if not exists rule_sets (group_id text, version integer, body text, text text, note text, confirmed_by text, ts integer, primary key (group_id, version));
create table if not exists cycles (group_id text, n integer, date text, recipient text, pot real, status text, due_ts integer, primary key (group_id, n));
create table if not exists ledger (id text primary key, group_id text, cycle integer, kind text, member text, amount real, status text, ts integer, paypal_id text,
  rule_version integer, rule text, approver text, simulated integer default 0, explanation text, checks text);
create table if not exists approvals (id text primary key, group_id text, kind text, title text, body text, amount real, needs text, checks text, payload text, ts integer);
create table if not exists timeline (id text primary key, group_id text, ts integer, tone text, title text, body text, why text);
create table if not exists audit (group_id text, seq integer, ts integer, actor text, action text, detail text, prev text, hash text, primary key (group_id, seq));
create table if not exists chat (id text primary key, group_id text, ts integer, sender text, who text, text text, checks text, blocked integer default 0, approval_id text, source text);
create table if not exists events (event_id text primary key, group_id text, ts integer, type text);
create table if not exists skips (group_id text, member text, cycle integer, primary key (group_id, member, cycle));
create table if not exists payouts (group_id text, cycle integer, recipient text, batch_id text, sender_batch_id text unique, amount real, status text, ts integer, primary key (group_id, cycle, recipient));
create table if not exists users (id text primary key, email text unique, name text, pw text, salt text, sandbox integer default 0, created_ts integer);
create table if not exists sessions (token text primary key, user_id text, ts integer);
create table if not exists invites (code text primary key, group_id text, name text, email text, status text, user_id text, ts integer);
create table if not exists model_config (group_id text primary key, provider text, base_url text, model text, api_key text);
create table if not exists invoices (id text primary key, group_id text, cycle integer, member text, amount real, status text, ts integer, reminders integer default 0, purpose text default 'catchup');
create table if not exists repayments (id text primary key, group_id text, member text, due_cycle integer, amount real, status text, invoice_id text);
"""
JSON_COLS = {"body", "checks", "needs", "payload"}


class Store:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.db.executescript(SCHEMA)
        for col, ddl in (("status", "text default 'active'"), ("treasurer", "integer default 1"), ("owner", "text")):   # databases created before accounts existed
            if col not in {r["name"] for r in self.db.execute("pragma table_info(groups)")}:
                self.db.execute(f"alter table groups add column {col} {ddl}")
        if "source" not in {r["name"] for r in self.db.execute("pragma table_info(chat)")}:
            self.db.execute("alter table chat add column source text")
        if "purpose" not in {r["name"] for r in self.db.execute("pragma table_info(invoices)")}:
            self.db.execute("alter table invoices add column purpose text default 'catchup'")
        for col, ddl in (("sub_status", "text default 'ACTIVE'"), ("approve_url", "text")):
            if col not in {r["name"] for r in self.db.execute("pragma table_info(members)")}:
                self.db.execute(f"alter table members add column {col} {ddl}")
        self.db.commit()

    def _enc(self, k: str, v: Any) -> Any:
        return json.dumps(v) if k in JSON_COLS and not isinstance(v, str) else (int(v) if isinstance(v, bool) else v)

    def _dec(self, row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        d = dict(row)
        for k in JSON_COLS & d.keys():
            if isinstance(d[k], str):
                try:
                    d[k] = json.loads(d[k])
                except ValueError:
                    pass
        return d

    def insert(self, table: str, row: dict, replace: bool = False) -> None:
        with self.lock:
            cols = ", ".join(row)
            q = f"insert {'or replace ' if replace else ''}into {table} ({cols}) values ({', '.join('?' for _ in row)})"
            self.db.execute(q, [self._enc(k, v) for k, v in row.items()])
            self.db.commit()

    def update(self, table: str, where: dict, patch: dict) -> None:
        with self.lock:
            q = f"update {table} set {', '.join(k + '=?' for k in patch)} where {' and '.join(k + '=?' for k in where)}"
            self.db.execute(q, [self._enc(k, v) for k, v in patch.items()] + list(where.values()))
            self.db.commit()

    def one(self, table: str, **where: Any) -> dict | None:
        with self.lock:
            q = f"select * from {table} where {' and '.join(k + '=?' for k in where)}"
            return self._dec(self.db.execute(q, list(where.values())).fetchone())

    def all(self, table: str, order: str = "", **where: Any) -> list[dict]:
        with self.lock:
            q = f"select * from {table}" + (f" where {' and '.join(k + '=?' for k in where)}" if where else "") + (f" order by {order}" if order else "")
            return [self._dec(r) for r in self.db.execute(q, list(where.values())).fetchall()]

    def delete_group(self, gid: str) -> None:
        with self.lock:
            for t in ("groups", "members", "rule_sets", "cycles", "ledger", "approvals", "timeline", "audit", "chat", "events", "skips", "payouts", "invoices", "invites", "repayments", "model_config"):
                self.db.execute(f"delete from {t} where " + ("id" if t == "groups" else "group_id") + "=?", (gid,))
            self.db.commit()

    def bump(self, gid: str) -> int:
        with self.lock:
            self.db.execute("update groups set version = version + 1 where id=?", (gid,))
            self.db.commit()
            r = self.db.execute("select version from groups where id=?", (gid,)).fetchone()
            return r[0] if r else 0
