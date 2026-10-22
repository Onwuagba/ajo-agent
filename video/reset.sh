#!/usr/bin/env bash
# Clean slate for a recording: stop the API, delete its database, start it again (PayPal simulator mode).
cd "$(dirname "$0")/../server" || exit 1
pkill -f "uvicorn ajo.api" 2>/dev/null; sleep 1
rm -f ajo.db ajo.db-journal
(nohup ./run.sh > /tmp/ajo-api.log 2>&1 &)
for i in $(seq 1 20); do curl -s -m 1 localhost:8100/api/health >/dev/null && break; sleep 1; done
curl -s localhost:8100/api/health; echo
