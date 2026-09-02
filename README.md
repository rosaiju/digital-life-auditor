# Digital Life Auditor

An AI-powered subscription scanner that connects to your bank via Plaid, automatically detects recurring charges, and uses GPT-4o to surface actionable spending insights.

## Stack

| Layer | Tech |
|---|---|
| Mobile | Expo (React Native) + TypeScript |
| Backend | FastAPI (Python) |
| Database | PostgreSQL + SQLAlchemy |
| Orchestration | Apache Airflow |
| Bank Data | Plaid API |
| AI Insights | OpenAI GPT-4o |
| Auth | JWT (python-jose + bcrypt) |
| Containerization | Docker + Docker Compose |

## Features

- **Subscription Scanner** — detects recurring charges from real bank data using a custom interval-classification algorithm
- **AI Insights** — GPT-4o categorizes subscriptions, flags redundant services, and surfaces the top savings opportunity
- **Airflow Pipeline** — daily DAG syncs all users' transactions at 2 AM UTC automatically
- **Plaid Sandbox** — fully testable without a real bank account
- **JWT Auth** — register/login flow with secure token storage on device

## Architecture

```
digital-life-auditor/
├── backend/                    # FastAPI Python API
│   └── app/
│       ├── models/             # SQLAlchemy ORM (users, plaid_items, transactions, subscriptions, insights)
│       ├── routers/            # auth, plaid, subscriptions, insights
│       └── services/           # plaid_service, subscription_detector, ai_insights
├── airflow/
│   └── dags/
│       └── sync_transactions_dag.py   # Daily Plaid sync for all users
├── mobile/                     # Expo React Native app
│   ├── app/                    # Expo Router screens
│   ├── components/             # SubscriptionCard, SummaryBanner, InsightCard, EmptyState
│   ├── hooks/                  # useSubscriptions, useInsights (React Query)
│   └── store/                  # Zustand auth store
├── scripts/
│   └── init-multiple-dbs.sh   # Creates postgres + airflow DBs on first run
└── docker-compose.yml
```

## Detection Algorithm

`subscription_detector.py` works in 5 steps:

1. **Normalize** merchant names (strips `.com`, `USA`, trailing digits, special chars)
2. **Group** transactions by normalized merchant
3. **Filter** for amount variance ≤ 10% (catches minor price changes)
4. **Classify** interval between charges into: weekly (7d), biweekly (14d), monthly (30d), quarterly (90d), annual (365d)
5. **Score** confidence based on occurrence count + interval tightness
6. Cross-reference with `known_subscriptions.json` (30+ services with cancel URLs)

## Getting Started

### 1. Clone & configure

```bash
git clone https://github.com/rosaiju/digital-life-auditor.git
cd digital-life-auditor
cp backend/.env.example backend/.env
# Fill in: PLAID_CLIENT_ID, PLAID_SECRET, OPENAI_API_KEY, JWT_SECRET
```

### 2. Start everything

```bash
docker compose up --build
```

Services:
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Airflow UI: http://localhost:8080 (admin/admin)

### 3. Run mobile app

```bash
cd mobile
npm install
npx expo start
```

### 4. Test with Plaid Sandbox

In the app → Connect Bank → Chase → use `user_good` / `pass_good`

Plaid sandbox pre-seeds recurring Netflix, Spotify, and gym membership transactions.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Get JWT token |
| GET | `/auth/me` | Current user |
| POST | `/plaid/link-token` | Create Plaid Link token |
| POST | `/plaid/exchange` | Exchange public token + trigger sync |
| POST | `/plaid/sync` | Manual resync |
| GET | `/subscriptions` | List detected subscriptions |
| PATCH | `/subscriptions/{id}/dismiss` | Hide a subscription |
| GET | `/insights` | Get latest AI insights |
| POST | `/insights/generate` | Generate new AI insights |

## Skills Demonstrated

- **Python / FastAPI** — REST API, dependency injection, middleware
- **PostgreSQL + SQLAlchemy** — relational modeling, ORM, migrations
- **ETL Pipeline** — Plaid → normalize → detect → store
- **Apache Airflow** — DAG authoring, scheduling, PythonOperator
- **Docker / Docker Compose** — multi-service containerization
- **OpenAI API** — structured JSON prompting, GPT-4o integration
- **React Native / Expo** — cross-platform mobile, Expo Router navigation
- **React Query + Zustand** — async state management, caching
- **JWT Auth** — stateless authentication, secure storage
- **Plaid API** — financial data aggregation, Link SDK
