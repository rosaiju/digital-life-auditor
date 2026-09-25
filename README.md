# Digital Life Auditor

[![CI](https://github.com/rosaiju/digital-life-auditor/actions/workflows/ci.yml/badge.svg)](https://github.com/rosaiju/digital-life-auditor/actions/workflows/ci.yml)

A mobile app that connects to your bank through Plaid, automatically detects recurring charges, and tells you where you can save money.

- **Subscription scanner**: finds subscriptions in real transaction data (weekly to annual), handles price changes, refunds and merchant-name noise, and ignores bank fees, transfers and loan payments.
- **Actionable**: known services come with a category and a one-tap link to their cancellation page.
- **AI insights**: a language model (Groq) writes the summary and savings tips. Totals and the category breakdown are always computed in code, and a rule-based analysis takes over if the model is unavailable.
- **Stays current**: an Airflow DAG refreshes every connected bank daily, Plaid webhooks (optional) trigger a sync the moment new transactions arrive, and pull-to-refresh syncs on demand. A subscription whose charges stop is moved to "ended" and dropped from your monthly total, and comes back automatically if the charges resume.
- **Resilient to bank problems**: each bank syncs independently and records its own health. If a bank's login expires the app shows a Reconnect banner and re-opens Plaid Link in update mode instead of failing silently.
- **Account control**: change password, delete your account (revokes bank access at Plaid and erases your data), disconnect any bank.
- **Safe by default**: Plaid access tokens are encrypted at rest, passwords are bcrypt-hashed, auth endpoints are rate limited, webhooks must carry a valid Plaid signature, and every query is scoped to the signed-in user.

## Stack

| Layer | Tech |
|---|---|
| Mobile | Expo (React Native) + TypeScript, Expo Router, React Query, Zustand |
| Backend | FastAPI (Python 3.11), SQLAlchemy 2, Alembic |
| Database | PostgreSQL |
| Orchestration | Apache Airflow |
| Bank data | Plaid (`/transactions/sync`) |
| AI | Groq (`openai/gpt-oss-120b` by default) |
| Auth | JWT + bcrypt |
| Ops | Docker Compose, GitHub Actions |

## Architecture

```
 Expo app ──HTTPS/JWT──▶ FastAPI ──▶ PostgreSQL
    │                      │  ├──▶ Plaid  (link token, exchange, transactions/sync)
    │ Plaid Link (native)  │  └──▶ Groq   (insight narrative; rule-based fallback)
    ▼                      ▲  ▲
  Plaid ──webhooks────────▶│  │  POST /plaid/webhook  (signed by Plaid, verified)
                           │  │
                      Airflow DAG ── daily at 02:00 UTC → POST /plaid/sync-all  (shared secret)
```

```
digital-life-auditor/
├── backend/
│   ├── app/
│   │   ├── models/            # SQLAlchemy models (Plaid tokens use an encrypted column type)
│   │   ├── routers/           # auth, plaid, subscriptions, insights
│   │   ├── services/          # plaid_service, sync, subscription_detector, ai_insights, crypto, money
│   │   └── seed_demo.py       # realistic demo data, no bank needed
│   ├── alembic/               # database migrations
│   └── tests/                 # pytest suite
├── airflow/dags/              # daily sync DAG
├── mobile/                    # Expo app (app/, components/, hooks/, services/, store/, utils/)
├── docs/interactive-preview.html   # clickable mock-up of the app
├── MANUAL_QA.md               # step-by-step manual checks (what was verified, what still needs a person)
└── docker-compose.yml
```

## Quick start

**Prerequisites**

| Tool | Needed for |
|---|---|
| Docker (Compose v2) | the backend, Postgres and Airflow |
| Node 20+ and npm | the mobile app and its tests |
| JDK 17 and Android Studio (SDK + an emulator) | only for bank linking on Android (`npx expo run:android`) |
| Python 3.11 | only to run the backend tests outside Docker |
| A free [Plaid](https://dashboard.plaid.com) account | `PLAID_CLIENT_ID` and the **Sandbox** `PLAID_SECRET` (Team Settings, Keys). Sandbox is free and needs no approval |
| A free [Groq](https://console.groq.com) key | optional; without it insights use the built-in rule-based analysis |

### 1. Configure

```bash
git clone https://github.com/rosaiju/digital-life-auditor.git
cd digital-life-auditor
cp backend/.env.example backend/.env     # add PLAID_CLIENT_ID / PLAID_SECRET / JWT_SECRET (+ GROQ_API_KEY)
cp .env.example .env                      # AIRFLOW_SYNC_SECRET, shared by Airflow and the backend
```

### 2. Start the backend

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| API | http://localhost:8000 (docs at `/docs`) |
| Airflow | http://localhost:8080 (admin / admin) |

The backend applies database migrations automatically on start.

### 3. Try it without a bank (demo data)

```bash
docker compose exec backend python -m app.seed_demo
```

This creates `demo@example.com` / `demo-password` with about 14 months of realistic transactions (Netflix, Spotify, a price increase, an annual Adobe charge, a refund, a cancelled Peloton membership, plus everyday spending). Sign in with it in the app to see detection, insights and cancel links working; the cancelled subscription shows up in the "ended" note rather than the total. Use `--reset` to recreate it.

**Suggested demo script (about 3 minutes, no bank needed):** sign in as the demo user, point out the monthly total and the price-increase subscription (Disney+), tap **Cancel plan** on one to open its cancellation page, dismiss one and restore it from Settings, scroll to the bottom and expand **Ended** (the cancelled Peloton, kept out of the total), then open **Insights** and tap **Generate**. To show the real bank flow, connect Tartan Bank (see below) on the Android build.

### 4. Run the app

```bash
cd mobile
cp .env.example .env        # set EXPO_PUBLIC_API_URL (see the comments inside)
npm install
npm run web                 # browser: everything except bank linking
```

**Bank linking needs a development build.** Plaid Link is a native module, so it does not run in Expo Go or the browser:

```bash
npx expo run:android        # or: npx expo run:ios   (needs Android Studio / Xcode)
```

Android notes (the full flow, including real Plaid Link, was driven on an emulator; see [MANUAL_QA.md](MANUAL_QA.md)):
- Use **JDK 17** (`JAVA_HOME`). Android Studio's bundled JDK 25 is too new for the Gradle version React Native 0.76 uses.
- The first build takes 20+ minutes; later ones are incremental.
- On a 16 KB-page emulator image Android shows an "app isn't 16 KB compatible" notice. It is expected with React Native 0.76 and harmless.
- The emulator reaches your backend at `http://10.0.2.2:8000` (`EXPO_PUBLIC_API_URL`). If the app cannot load its JavaScript from Metro, run `adb reverse tcp:8081 tcp:8081`.
- After the first build only Metro is needed (`npx expo start --dev-client`), unless you add a native dependency.

**Plaid sandbox:** in Link, search for **Tartan Bank** and sign in with `user_transactions_dynamic` / `pass_good`. That user has recurring charges, so subscriptions appear. Banks that use OAuth (Chase and other big banks) open a browser, and on Android they need the app's package name registered in Plaid, see [Bank OAuth on Android](#bank-oauth-on-android). The sandbox needs a moment to prepare transactions; if the list is empty right after connecting, pull down to refresh.

## Configuration

`backend/.env`:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres URL (docker compose overrides it) |
| `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV` | Plaid credentials; `sandbox`, `development` or `production` |
| `PLAID_ANDROID_PACKAGE_NAME` | Optional. Set to `com.rosaiju.digitallifeauditor` once registered in the Plaid dashboard (needed for bank OAuth on Android) |
| `PLAID_WEBHOOK_URL` | Optional. Public HTTPS URL of `POST /plaid/webhook`; see [Webhooks](#webhooks) |
| `JWT_SECRET` | Signs login tokens. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `TOKEN_ENCRYPTION_KEY` | Optional. Key for encrypting Plaid tokens at rest; defaults to one derived from `JWT_SECRET` |
| `GROQ_API_KEY`, `GROQ_MODEL` | Optional. Without a key, insights use the rule-based analysis |
| `CORS_ORIGINS` | Comma-separated allowed origins (`*` for local development only) |
| `AUTH_RATE_LIMIT_PER_MINUTE` | Max login/register attempts per client address per minute (default 20, `0` disables). In-memory, per process |

Root `.env`: `AIRFLOW_SYNC_SECRET`, used by both Airflow and the backend.

With `PLAID_ENV` set to `development` or `production` the API refuses to start unless `JWT_SECRET` is random and at least 32 characters, `AIRFLOW_SYNC_SECRET` is not the placeholder, and `CORS_ORIGINS` lists explicit origins.

> Groq retires models from time to time. If insights say "rule-based analysis" and the logs show `model_not_found`, list your available models and set `GROQ_MODEL`.

## How subscription detection works

`backend/app/services/subscription_detector.py`:

1. **Normalize merchants**: `NETFLIX.COM`, `Netflix Inc` and `NETFLIX*A1B2` are the same merchant.
2. **Filter**: drop refunds/credits and non-subscription Plaid categories (bank fees, transfers, income, loan payments); collapse same-day duplicates.
3. **Check the amount**: charges within 10% of each other count as the same. After a price change, the newest run of similar charges is used (needs 3+ to be trusted).
4. **Classify the interval**: weekly, biweekly, monthly, quarterly or annual, with tolerance for calendar drift.
5. **Require enough evidence**: an unrecognised merchant needs 3+ charges unless it is quarterly/annual; a known service needs only 2.
6. **Score confidence** from the number of charges and how regular the gaps are.
7. **Enrich** known services (about 30) with display name, category and cancel URL, matched on whole words only.

## API

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | Create account / get a JWT (rate limited) |
| GET | `/auth/me` | Current user |
| POST | `/auth/change-password`, `/auth/delete-account` | Both re-check the password; deleting also revokes bank access at Plaid |
| POST | `/plaid/link-token` | Start Plaid Link |
| POST | `/plaid/exchange` | Exchange the public token, store the connection, run the first sync |
| POST | `/plaid/sync` | Sync the user's banks now; one failing bank does not stop the others |
| GET, DELETE | `/plaid/items`, `/plaid/items/{id}` | List banks with health (`ok` / `login_required` / `error`, last synced) / disconnect (revokes the token at Plaid) |
| POST | `/plaid/items/{id}/link-token`, `/plaid/items/{id}/reconnected` | Reconnect a bank whose login expired (Link update mode), then re-sync |
| POST | `/plaid/webhook` | Plaid only; the `Plaid-Verification` signature is checked |
| POST | `/plaid/sync-all` | Airflow only, protected by a shared secret |
| GET | `/subscriptions?status=active\|dismissed\|ended\|all` | Detected subscriptions, most expensive first |
| PATCH | `/subscriptions/{id}/dismiss`, `/restore` | Hide / unhide |
| GET, POST | `/insights`, `/insights/generate` | Latest / new insights |
| GET | `/health` | Liveness plus a database check |

## Development

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                                                   # 160+ tests; SQLite, Plaid and Groq are mocked

alembic revision --autogenerate -m "describe change"    # after editing models
alembic upgrade head
```

```bash
cd mobile
npm run typecheck
npm test                                                 # 85+ tests: store, API client, every screen (Jest + Testing Library)
```

CI (GitHub Actions) runs the backend tests on Python 3.11, applies and checks the migrations against real Postgres, typechecks and unit-tests the app and bundles it for web and Android, and smoke-tests `docker compose`.

What the automated tests do **not** cover: the native Plaid Link screen itself (the tests mock the SDK), real bank data beyond the Plaid sandbox, and iOS.

**Verification status.** Driven by hand on an Android emulator against the real Plaid sandbox: sign-up, sign-in, connecting Tartan Bank, sync and repeated sync, subscriptions and insights, dismiss and restore, pull-to-refresh, two banks at once, a partial failure, **Reconnect through Plaid Link update mode** (after forcing the Item into login-required with `/sandbox/item/reset_login`), disconnect and reconnect, sign-out and sign-in as a different user, change password, account deletion (data gone, Plaid token revoked), and an invalid session. Also verified against real Postgres: the 0001 to 0002 migration on a database with data, a full up/down round trip, and two concurrent syncs of one bank. **Not** verified: webhook delivery from Plaid (needs a public URL), a physical device, bank OAuth, iOS. Exact steps for those, and a regression checklist for the rest, are in [MANUAL_QA.md](MANUAL_QA.md).

## Webhooks

Without webhooks the app still works: transactions refresh daily (Airflow), on pull-to-refresh and via **Settings, Sync Transactions Now**. Webhooks make it near real-time and let Plaid tell the app when a bank needs a new login.

1. Expose the backend over HTTPS, e.g. `ngrok http 8000`.
2. Set `PLAID_WEBHOOK_URL=https://<your-host>/plaid/webhook` in `backend/.env` and restart. New link tokens now carry the URL (banks connected earlier need to be reconnected once, or use Plaid's `/item/webhook/update`).
3. In the sandbox you can fire one on demand with Plaid's `/sandbox/item/fire_webhook`.

Every request must carry a valid `Plaid-Verification` JWT (ES256, fresh, body hash matches, key not expired), otherwise it gets a 401. `SYNC_UPDATES_AVAILABLE` triggers a background sync; `ITEM_LOGIN_REQUIRED`, `PENDING_EXPIRATION` and `USER_PERMISSION_REVOKED` flag the bank for reconnection. The signature check is covered by tests using a locally generated key, and the real `webhook_verification_key/get` request was exercised against the sandbox; delivery from real Plaid has not been exercised (steps in [MANUAL_QA.md](MANUAL_QA.md#22-plaid-webhooks-end-to-end-needs-a-public-https-url)). Signing keys are cached for an hour, an unknown key id is a 401 (not an outage), and bodies over 64 KB are rejected with 413. Repeated deliveries are harmless because every handler is idempotent (syncs are cursor based).

## Bank OAuth on Android

Big banks (Chase, etc.) authenticate in the browser and then redirect back to the app by its **Android package name**. Plaid only allows that for registered package names:

1. Plaid dashboard, **Developers, API, Allowed Android package names**, add `com.rosaiju.digitallifeauditor`.
2. Set `PLAID_ANDROID_PACKAGE_NAME=com.rosaiju.digitallifeauditor` in `backend/.env` and restart the backend.

Until then, Plaid rejects the link token (`INVALID_FIELD: Android package name must be configured in the developer dashboard`) if the package name is sent, and if it is not sent, the OAuth page ends at "close this page and continue" and the connection never reaches the app. Non-OAuth banks (Tartan Bank in the sandbox) work without any of this.

## Troubleshooting

- **The app shows "Can't reach the server"**: the backend is down or `EXPO_PUBLIC_API_URL` is wrong (emulator `http://10.0.2.2:8000`, phone `http://<LAN-ip>:8000`; the backend must listen on `0.0.0.0`, which the Docker setup does).
- **A bank shows "Sign-in needed"**: expected when the bank asks for a new login. Tap **Reconnect**. To provoke it in the sandbox see [MANUAL_QA.md](MANUAL_QA.md#21-helper-force-the-sandbox-into-a-login-required-state).
- **`relation ... already exists` / schema errors after updating**: the schema is now managed by Alembic. For a throwaway dev database, reset it with `docker compose down -v` and start again.
- **Android emulator can't reach the API**: use `EXPO_PUBLIC_API_URL=http://10.0.2.2:8000`. On a physical device use your computer's LAN address.
- **Airflow gets 403 from the backend**: `AIRFLOW_SYNC_SECRET` must come from the root `.env` so both services see the same value.

## Security notes and limits

Built and tested against the **Plaid sandbox**. Before handling real accounts you would want: HTTPS in front of the API, a managed secret store and key rotation, a shared rate limiter if you run several API replicas (the built-in one is per process), server-side token revocation (JWTs are stateless and last 7 days, so a stolen token stays valid until it expires even after a password change), and Plaid production approval. Auth endpoints are rate limited, and non-sandbox environments refuse to start with placeholder secrets or wildcard CORS. Insight generation sends only merchant names, amounts and categories to the language model, never bank credentials or account numbers.
