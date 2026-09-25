# Digital Life Auditor

[![CI](https://github.com/rosaiju/digital-life-auditor/actions/workflows/ci.yml/badge.svg)](https://github.com/rosaiju/digital-life-auditor/actions/workflows/ci.yml)

A mobile app that connects to your bank through Plaid, automatically detects recurring charges, and tells you where you can save money.

- **Subscription scanner**: finds subscriptions in real transaction data (weekly to annual), handles price changes, refunds and merchant-name noise, and ignores bank fees, transfers and loan payments.
- **Actionable**: known services come with a category and a one-tap link to their cancellation page.
- **AI insights**: a language model (Groq) writes the summary and savings tips. Totals and the category breakdown are always computed in code, and a rule-based analysis takes over if the model is unavailable.
- **Automatic sync**: an Airflow DAG refreshes every connected bank daily.
- **Safe by default**: Plaid access tokens are encrypted at rest, passwords are bcrypt-hashed, every query is scoped to the signed-in user.

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
    ▼                      ▲
  Plaid                    │  POST /plaid/sync-all  (shared secret)
                      Airflow DAG  ── daily at 02:00 UTC
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
└── docker-compose.yml
```

## Quick start

You need Docker, Node 20+, and (optionally) free [Plaid sandbox](https://dashboard.plaid.com) and [Groq](https://console.groq.com) keys.

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

This creates `demo@example.com` / `demo-password` with about 14 months of realistic transactions (Netflix, Spotify, a price increase, an annual Adobe charge, a refund, plus everyday spending). Sign in with it in the app to see detection, insights and cancel links working. Use `--reset` to recreate it.

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

Android notes (tested on an emulator):
- Use **JDK 17** (`JAVA_HOME`). Android Studio's bundled JDK 25 is too new for the Gradle version React Native 0.76 uses.
- The first build takes 20+ minutes; later ones are incremental.
- On a 16 KB-page emulator image Android shows an "app isn't 16 KB compatible" notice. It is expected with React Native 0.76 and harmless.
- The emulator reaches your backend at `http://10.0.2.2:8000` (`EXPO_PUBLIC_API_URL`).

**Plaid sandbox:** in Link, search for **Tartan Bank** and sign in with `user_transactions_dynamic` / `pass_good`. That user has recurring charges, so subscriptions appear. Banks that use OAuth (Chase and other big banks) open a browser, and on Android they need the app's package name registered in Plaid, see [Bank OAuth on Android](#bank-oauth-on-android). The sandbox needs a moment to prepare transactions; if the list is empty right after connecting, pull down to refresh.

## Configuration

`backend/.env`:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres URL (docker compose overrides it) |
| `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV` | Plaid credentials; `sandbox`, `development` or `production` |
| `PLAID_ANDROID_PACKAGE_NAME` | Optional. Set to `com.rosaiju.digitallifeauditor` once registered in the Plaid dashboard (needed for bank OAuth on Android) |
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
| POST | `/auth/register`, `/auth/login` | Create account / get a JWT |
| GET | `/auth/me` | Current user |
| POST | `/plaid/link-token` | Start Plaid Link |
| POST | `/plaid/exchange` | Exchange the public token, store the connection, run the first sync |
| POST | `/plaid/sync` | Sync the user's connections now |
| GET, DELETE | `/plaid/items`, `/plaid/items/{id}` | List / disconnect banks (revokes the token at Plaid) |
| POST | `/plaid/sync-all` | Airflow only, protected by a shared secret |
| GET | `/subscriptions?status=active\|dismissed\|all` | Detected subscriptions, most expensive first |
| PATCH | `/subscriptions/{id}/dismiss`, `/restore` | Hide / unhide |
| GET, POST | `/insights`, `/insights/generate` | Latest / new insights |
| GET | `/health` | Liveness plus a database check |

## Development

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                                                   # 100+ tests; SQLite, Plaid and Groq are mocked

alembic revision --autogenerate -m "describe change"    # after editing models
alembic upgrade head
```

```bash
cd mobile
npm run typecheck
```

CI (GitHub Actions) runs the backend tests on Python 3.11, applies and checks the migrations against real Postgres, typechecks the app and bundles it for web and Android, and smoke-tests `docker compose`.

## Bank OAuth on Android

Big banks (Chase, etc.) authenticate in the browser and then redirect back to the app by its **Android package name**. Plaid only allows that for registered package names:

1. Plaid dashboard, **Developers, API, Allowed Android package names**, add `com.rosaiju.digitallifeauditor`.
2. Set `PLAID_ANDROID_PACKAGE_NAME=com.rosaiju.digitallifeauditor` in `backend/.env` and restart the backend.

Until then, Plaid rejects the link token (`INVALID_FIELD: Android package name must be configured in the developer dashboard`) if the package name is sent, and if it is not sent, the OAuth page ends at "close this page and continue" and the connection never reaches the app. Non-OAuth banks (Tartan Bank in the sandbox) work without any of this.

## Troubleshooting

- **`relation ... already exists` / schema errors after updating**: the schema is now managed by Alembic. For a throwaway dev database, reset it with `docker compose down -v` and start again.
- **Android emulator can't reach the API**: use `EXPO_PUBLIC_API_URL=http://10.0.2.2:8000`. On a physical device use your computer's LAN address.
- **Airflow gets 403 from the backend**: `AIRFLOW_SYNC_SECRET` must come from the root `.env` so both services see the same value.

## Security notes and limits

Built and tested against the **Plaid sandbox**. Before handling real accounts you would want: HTTPS in front of the API, a managed secret store and key rotation, Plaid webhooks (instead of only polling) for real-time updates, a shared rate limiter if you run several API replicas (the built-in one is per process), and Plaid production approval. Auth endpoints are rate limited, and non-sandbox environments refuse to start with placeholder secrets or wildcard CORS. Insight generation sends only merchant names, amounts and categories to the language model, never bank credentials or account numbers.
