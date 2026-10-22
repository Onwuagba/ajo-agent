# Ajo server

The treasurer behind the Ajo front end. **The AI interprets; the rules engine decides; every decision is logged.**

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
pytest
./run.sh                    # http://127.0.0.1:8100, API docs at /docs
```

With no configuration it uses an in-process **PayPal simulator** and a **rules-based parser**, starts with an empty database (register, create a circle, invite friends),
and needs no keys. Copy `.env.example` to `.env` to switch on the real sandbox or a model.

## What is real and what is simulated

| Part | State |
|---|---|
| Rules engine, payout checks, state machine, approvals, late ladder, swap and hardship logic | Real code, covered by tests |
| Audit log | Real SHA-256 hash chain, verified on demand. Tamper-evident, not immutable |
| Money-out guard | One function sends money; it refuses without a cleared proposal; SQLite uniqueness stops a second payout per group, cycle and recipient |
| PayPal (default) | **Simulator** (`ajo/paypal/fake.py`). Events are HMAC-signed with a demo secret, not PayPal's scheme, and are labelled simulated |
| PayPal sandbox client | Written from PayPal's public docs (`ajo/paypal/real.py`), tested only against a mocked HTTP transport. **Not yet run against a live sandbox**; every method is a [VERIFY] item until it has |
| Model | Optional. Auto-detects a local Ollama model; otherwise a rules-based reader runs, and every reply says which one read it. The model only classifies and phrases; code validates it, and an attack screen runs first and cannot be overruled |
| Auth | Salted-scrypt accounts and bearer sessions; the acting member always comes from the session. Demo-grade (no email verification, no rate limiting) |

## API (the front end uses these)

Every group route needs `Authorization: Bearer <token>` from a signed-in member of that group. The acting member always comes from the session, never from the request body.

| Method and path | Purpose |
|---|---|
| `POST /api/auth/register`, `/login`, `/logout`, `GET /api/auth/me` | Accounts (salted scrypt) and bearer sessions |
| `GET /api/me/groups`, `POST /api/groups` | Your circles; start one (it begins as `forming`, with no PayPal plan or cycles) |
| `POST /api/groups/{id}/invites`, `DELETE .../invites/{code}` | Organiser creates or withdraws one-use invite links |
| `GET /api/invites/{code}`, `POST /api/invites/{code}/accept` | Look up an invite (public, limited) and join |
| `POST /api/groups/{id}/treasurer` | Organiser confirms the rules and appoints the AI treasurer |
| `POST /api/groups/{id}/activate` | Organiser starts the circle: draw the order, create the plan and one subscription per member. The circle is `starting` until every member has approved theirs, then `active` |
| `POST /api/groups/{id}/subscription/approve` | Simulator only: the member approves their own subscription. With real PayPal the member follows `payment.approveUrl` and PayPal's `BILLING.SUBSCRIPTION.ACTIVATED` webhook does this |
| `GET /api/groups/{id}/state` | Everything the UI shows. `version` changes on every write, so polling is cheap |
| `POST /api/groups/{id}/rules/parse` / `confirm` | Plain English to rules (with questions and conflicts); organiser confirms a new version |
| `POST /api/groups/{id}/chat` | A member's message: swap, hardship, explain, or an instruction that is blocked and logged |
| `POST /api/groups/{id}/approvals/{aid}/decide` | Approve or decline. Only the named person can answer |
| `POST /api/groups/{id}/tick` | Run the late ladder. Also runs every 30 s in the background. Idempotent |
| `POST /api/webhooks/paypal` | Verified first, then handled. Duplicate events are ignored |
| `GET /api/groups/{id}/audit/verify`, `/audit/replay/{n}` | Chain check; replay a paid cycle's decision from the log |
| `POST /api/sandbox/{id}/join-friends`, `/pay`, `/fail`, `/pay-invoice`, `/advance`, `/tamper/{seq}` | Simulator (PAYPAL_MODE=fake only; 404 otherwise). The `X-Act-As` header lets the organiser act as a sandbox friend |

## How a payout is protected

1. A webhook is verified, then deduplicated by event id, then matched to a member by subscription id.
2. When the pot is fully funded the engine builds a proposal and runs seven hard checks (right recipient, amount equals the pot,
   no earlier payout, good standing, nothing outstanding, under the cap, came from the engine and not from chat text).
3. Any failed hard check blocks it; there is no override. Over the approval threshold it waits for a named human.
4. `_execute_payout` is the only sender. It needs a cleared proposal, claims the unique (group, cycle, recipient) row first, and uses
   a deterministic `sender_batch_id` so a retry cannot pay twice. A failed payout never marks the cycle paid.

## Known limits

- No real authentication or per-member permissions beyond "this request is waiting on you".
- Changing the amount or cycle length mid-rotation is refused (it would need new PayPal subscriptions).
- Member emails are used as PayPal receivers; address verification is assumed, not checked.
- Pooled-funds regulation and PayPal acceptable-use terms are not addressed by code. Sandbox only.


## Checking the PayPal calls

`scripts/verify_paypal.py` runs every PayPal call Ajo makes against the **sandbox** (it refuses any other base URL) and prints PASS/FAIL per call. Put a sandbox REST app's `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` in `.env`, then `.venv/bin/python scripts/verify_paypal.py --payout-to <sandbox personal account email>`.

## The treasurer's model

The chat is read by a language model when one is available, and says which reader answered under every reply ("Read by: ..."). The model only interprets and phrases; the rules engine checks and decides, and a deterministic attack screen always runs first and cannot be overruled by a model.

- **Default (`AJO_LLM=auto`)**: use a local [Ollama](https://ollama.com) if it is running (prefers `llama3.2:3b`, then `llama3.1:8b`, `qwen3:8b`, then any installed chat model); otherwise built-in rules, labelled as such.
- **Per circle**: the organiser picks the model on the Rules page: any model installed in Ollama, an OpenAI-compatible service (address, model, key), or Anthropic. Keys are stored server-side for that circle, never returned to the browser and never written to the audit log. "Test the model" checks it end to end.
- **Server-wide**: `AJO_LLM=ollama|openai_compat|anthropic|none`, `AJO_OLLAMA_URL`, `AJO_LLM_MODEL`.
- A model that is slow or unreachable times out after 35 s and the rules reader answers, so the chat never hangs.
