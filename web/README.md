# Ajo web (front end)

The Ajo treasurer app: a rotating-savings circle where an AI agent proposes and explains, and a deterministic rules engine decides.
It is a real app with accounts, not a scripted demo: you register, start a circle, invite people with links, appoint the AI treasurer
by confirming the rules, and start the rotation. It needs the Ajo API (`VITE_API_URL`, default `http://127.0.0.1:8100`); without it
the app says so. See `../docs/FEATURES.md` for the full plan.

## Run

For live mode start the API first (`../server/run.sh`), then the app.

```bash
npm install
npm run dev        # http://localhost:5180
npm run build      # type-check and production build into dist/
```

## The flow

1. **Create an account** (or open an invite link, which brings you straight to the circle).
2. **Start a circle**: name, number of people, amount, how often.
3. **Invite your people**: each invite is a one-use link. The roster fills as people join.
4. **Appoint the AI treasurer**: write the rules in plain English, press *Turn into rules*, read what the engine will enforce (with any
   questions or conflicts), then appoint. Nothing is subscribed or scheduled until the organiser starts the circle.
5. **Start the circle**: the order is drawn at random with a recorded seed and a PayPal subscription is created for each member. **Each member approves their own** subscription (on PayPal's page with real PayPal; simulated in the sandbox). The first cycle starts when all have approved.
6. **Run it**: Overview, Ledger (AG Grid, click a row for *why this payment*), Schedule, Requests (chat with the treasurer; approvals),
   Rules, and Audit (a SHA-256 hash chain checked in the browser).

## The sandbox simulator

One person can't be five members and PayPal at once, so the app has a clearly labelled **Sandbox simulator** (bottom right, only when the
API runs the PayPal simulator): let sandbox friends accept invites, send a payment or a failure for any member, pay an invoice, move time
forward, and *view as* a sandbox member to approve or chat as them. Every event goes through the same signed-webhook path a real PayPal
event would. With `PAYPAL_MODE=sandbox` the simulator is off and PayPal's sandbox sends the events.

## Structure

- `src/state/store.ts`: one small store: session, hash routing, the open group (polled), API calls, the simulator calls, the audit-chain check.
- `src/data/roster.ts`: the open group's members and summary, filled from the API.
- `src/pages/*`: Auth (landing and form), Groups, NewGroup, Join, Setup, then the dashboard pages Overview, Ledger, Schedule, Requests, Rules, Audit.
- `src/components/*`: the AG Grid ledger, drawer, timeline, approvals, cycle stepper, shared UI.
- Design tokens (light and dark) are CSS variables at the top of `src/styles.css`.

## Honest limits

- Runs on the PayPal simulator until sandbox credentials are added; everything the simulator produces is labelled.
- The rule parser is rules-based unless a model is configured on the server.
- The hash chain is real and verified in the browser from the entries the server sends.
- Not yet exercised end to end in a browser.
