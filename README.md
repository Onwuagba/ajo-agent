# Ajo: a savings circle with an AI treasurer

Built for the PayPal AI Hackathon. A rotating savings circle (ajo, susu, chama): everyone pays in each cycle and one person collects the pot. The weak point is whoever holds the money, so Ajo gives that job to a treasurer that cannot spend.

**The AI interprets; the rules engine decides; every decision is logged.**

- A model reads what members ask for in their own words. It can only classify and phrase. Code validates its output (numbers, dates and names must match), and a deterministic attack screen runs first and can't be overruled by a model.
- The rules engine checks every payout and allows only one function to send money, which refuses without a cleared proposal.
- Late payments, hardship skips with scheduled repayments, swaps and payouts follow the circle's rules and need the approvals those rules require.
- Every action goes into a SHA-256 hash-chained audit trail, verified in the browser.
- Each member approves their own PayPal subscription. By default a built-in PayPal simulator stands in for PayPal and time.

## Run it

```bash
cd server && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && ./run.sh   # API on :8100
cd web && npm install && npm run dev                                                                        # UI on :5180
```

No keys needed. If [Ollama](https://ollama.com) is running, Ajo uses a local model (for example `llama3.2:3b`); otherwise a rules-based reader runs and each reply says which one read it. A circle's organiser can switch to their own model (Ollama, any OpenAI-compatible API, or Anthropic) from the Rules page.

## Bring your own key

Ajo ships with no key. Whoever runs it chooses the model, in `server/.env` (or the host's environment):

| Where you run it | Set |
|---|---|
| Your machine with [Ollama](https://ollama.com) | nothing; it finds a local model automatically (`AJO_LLM=auto`), or set `AJO_LLM=ollama` and `AJO_LLM_MODEL=llama3.2:3b` |
| Anywhere, with an OpenAI-compatible API (Nebius Token Factory, OpenAI, vLLM, LM Studio) | `AJO_LLM=openai_compat`, `AJO_LLM_BASE_URL`, `AJO_LLM_API_KEY`, `AJO_LLM_MODEL` |
| Anywhere, with Anthropic | `AJO_LLM=anthropic`, `AJO_LLM_API_KEY`, `AJO_LLM_MODEL` |
| No key | the built-in rules reader runs, and each reply says so |

A circle's organiser can also pick a model for that circle from the Rules page, with their own key (stored server-side, never returned to the browser).

## Deploy

- **API** (needs a process that stays up and a disk for SQLite): `render.yaml` and `server/Dockerfile` run it on Render, or on any Docker host. Set `AJO_CORS` to your web app's URL and the variables above. On Render's free plan the database resets when the service restarts; attach a disk (set `AJO_DB=/data/ajo.db`) to keep it.
- **Web** (static): `netlify.toml` builds `web/` on Netlify. In the Netlify site settings set `VITE_API_URL` to the API's URL, then redeploy.
- PayPal: keep `PAYPAL_MODE=fake` for the simulator, or `sandbox` with your own sandbox app's credentials; see `server/scripts/verify_paypal.py`.

## What's real and what isn't

The PayPal **simulator** is the default and is clearly labelled in the UI. The real sandbox client (`server/ajo/paypal/real.py`) has been run against the live PayPal sandbox with `server/scripts/verify_paypal.py`: OAuth, billing plan, subscription with approval link, invoice create, send and remind, payout batch and lookup, PayPal refusing a repeated payout batch, and webhook signature rejection all pass (2026-10-22). Incoming webhooks need a public URL. No real money moves anywhere. See [`server/README.md`](server/README.md) for the API and details, and [`docs/FEATURES.md`](docs/FEATURES.md) for the feature design.

The demo video was recorded and edited with the scripts in [`video/`](video/).

## Licence

MIT
