#!/usr/bin/env bash
# Start the API on :8100 using the PayPal simulator unless PAYPAL_MODE=sandbox is set in .env
cd "$(dirname "$0")" && . .venv/bin/activate && exec uvicorn ajo.api:app_factory --factory --host 127.0.0.1 --port "${PORT:-8100}" "$@"
