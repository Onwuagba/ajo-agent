"""A tamper-evident log: each entry stores the hash of the one before it. 'Tamper-evident', not 'immutable': the rows can still be edited, but the edit is detectable."""
import hashlib

from .store import Store

GENESIS = "0" * 64


def body(e: dict) -> str:
    return f"{e['seq']}|{e['ts']}|{e['actor']}|{e['action']}|{e['detail']}"


def digest(prev: str, e: dict) -> str:
    return hashlib.sha256((prev + body(e)).encode()).hexdigest()


def append(store: Store, gid: str, actor: str, action: str, detail: str, ts: int) -> dict:
    with store.lock:
        last = store.db.execute("select seq, hash from audit where group_id=? order by seq desc limit 1", (gid,)).fetchone()
        seq, prev = (last["seq"] + 1, last["hash"]) if last else (1, GENESIS)
        e = {"group_id": gid, "seq": seq, "ts": ts, "actor": actor, "action": action, "detail": detail[:600], "prev": prev}
        e["hash"] = digest(prev, e)
        store.insert("audit", e)
        return e


def verify(store: Store, gid: str) -> int | None:
    """Returns the first sequence number whose content or link does not match, or None when the chain is intact."""
    prev = GENESIS
    for e in store.all("audit", order="seq", group_id=gid):
        if e["prev"] != prev or e["hash"] != digest(prev, e):
            return e["seq"]
        prev = e["hash"]
    return None
