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

## What's real and what isn't

The PayPal **simulator** is the default and is clearly labelled in the UI. The real sandbox client (`server/ajo/paypal/real.py`) has been run against the live PayPal sandbox with `server/scripts/verify_paypal.py`: OAuth, billing plan, subscription with approval link, invoice create, send and remind, payout batch and lookup, PayPal refusing a repeated payout batch, and webhook signature rejection all pass (2026-10-22). Incoming webhooks need a public URL. No real money moves anywhere. See [`server/README.md`](server/README.md) for the API and details, and [`docs/FEATURES.md`](docs/FEATURES.md) for the feature design.

The demo video was recorded and edited with the scripts in [`video/`](video/).

## Licence

MIT
