# Manual QA

Automated tests (backend pytest, mobile Jest, CI) cover logic and screens with Plaid mocked. This file lists what
only a person with a device or a public URL can check, with exact steps. Section 1 is a regression walk-through of
what was already driven by hand on an Android emulator; section 2 is everything **not yet verified**.

## 0. Prerequisites

```bash
cp backend/.env.example backend/.env      # PLAID_CLIENT_ID, PLAID_SECRET (sandbox), JWT_SECRET, optional GROQ_API_KEY
cp .env.example .env
docker compose up --build -d              # postgres + backend (+ airflow); migrations run on start
docker compose exec backend python -m app.seed_demo      # demo@example.com / demo-password
cd mobile && cp .env.example .env && npm install
```

Android app (needs **JDK 17**; the first build takes 20+ minutes):

```bash
npx expo run:android                      # builds and installs the dev client, then starts Metro
# afterwards, only Metro is needed:  npx expo start --dev-client
```

Emulator: `EXPO_PUBLIC_API_URL=http://10.0.2.2:8000`. Physical device: your computer's LAN address. If Metro
cannot be reached from an emulator run `adb reverse tcp:8081 tcp:8081`. Android may show a harmless
"app isn't 16 KB compatible" dialog on first launch (React Native 0.76); tap *Don't Show Again*.

Plaid Link sandbox login (Tartan Bank): `user_transactions_dynamic` / `pass_good`. On the phone-number
screen tap *Continue without phone number*; at the end tap *Finish without saving*.

## 1. Regression walk-through (verified on the Android emulator, 2026-09-25)

Run this after any change to auth, sync, Plaid or the screens. Expected result in *italics*.

| # | Step | Expected |
|---|---|---|
| 1 | Sign up with a new email and an 8+ character password | *Lands on Subscriptions; empty state with **Connect Bank*** |
| 2 | Sign up again with the same email | *"Email already registered"* |
| 3 | Subscriptions, **Connect Bank**, **Connect a Bank Account**, Tartan Bank, log in | *"Connected! Scanned your transactions and found 3 subscriptions."* Then ChatGPT $20.00, Netflix $19.57, Spotify $12.65, total $52.22 |
| 4 | Tap the **x** on Spotify, then **Cancel** in the dialog | *Nothing changes* |
| 5 | Tap **x** on Spotify, then **Dismiss** | *Spotify disappears; total $39.57, 2 subscriptions* |
| 6 | Settings, **Restore dismissed** | *Count goes 1 to 0; Spotify is back, total $52.22* |
| 7 | Settings, **Sync Transactions Now** (twice) | *"Everything is up to date."* No duplicate subscriptions |
| 8 | Subscriptions: pull down | *Spinner, list reloads, no error* |
| 9 | AI Insights, **Generate** | *Summary, $52.22 / $626.64 / 3, tips; savings badges show cents (Save $12.65/mo)* |
| 10 | Force a login-required state (section 2.1 helper), then pull to refresh | *Yellow "Tartan Bank needs you to sign in again" banner with **Reconnect**; **no** second red error banner; Settings shows "Sign-in needed"* |
| 11 | Tap **Reconnect**, *Sign in to your bank again*, continue without phone, password `pass_good`, Submit, Finish without saving | *"Reconnected: Your bank is syncing again."* Banner gone; Settings shows "Synced just now" |
| 12 | Connect a second Tartan Bank, force login-required on only one, pull to refresh | *One Reconnect banner, total unchanged; Settings shows one bank OK and one "Sign-in needed"* |
| 13 | Settings, **Disconnect** each bank, confirm | *Rows disappear. **Sync Now** then says "No bank connected"* |
| 14 | **Connect Bank Account** again | *Connects; still exactly 3 subscriptions* |
| 15 | Sign out (confirm), sign in as `demo@example.com` typed as ` Demo@Example.COM ` | *Signs in; 10 subscriptions, $183.84; **no** data from the other account* |
| 16 | Demo dashboard: scroll to the bottom, tap **Ended · 1** | *Peloton: "Last charged Jul 12 · was $44.00/mo" (dates shift with the seed date); not in the total* |
| 17 | Settings, **Change password**: wrong current password | *Inline "Incorrect password"* |
| 18 | Same screen with the right current password and a new one | *"Password updated"; back on Settings* |
| 19 | Sign out; sign in with the OLD password, then the NEW one | *Old: "Incorrect email or password"; new works* |
| 20 | Settings, **Delete account**, wrong password | *Inline "Incorrect password"* |
| 21 | Correct password, **Delete my account**, **Cancel** in the dialog | *Nothing deleted* |
| 22 | Again, **Delete forever** | *Back on the sign-in screen; signing in fails* |
| 23 | Stop the backend (`docker compose stop backend`), try to sign in | *"Can't reach the server. Check your connection and try again."* App recovers after `docker compose start backend` |
| 24 | While signed in, delete the user server-side (or wait for token expiry) and pull to refresh | *App returns to the sign-in screen* |

After step 22 confirm in Postgres that the user's rows are gone and Plaid revoked the token:
`docker compose exec postgres psql -U dlauser -d digital_life_auditor -c "select count(*) from plaid_items"`.

## 2. Not yet verified (needs you)

### 2.1 Helper: force the sandbox into a login-required state

Plaid's `/sandbox/item/reset_login` makes an Item demand a new login (this is how step 10 above was tested):

```bash
docker compose exec -T backend python - <<'EOF'
from plaid.model.sandbox_item_reset_login_request import SandboxItemResetLoginRequest
from app.database import SessionLocal
from app.models.connection import PlaidItem
from app.services import plaid_service

with SessionLocal() as db:
    for item in db.query(PlaidItem).all():      # add .filter(PlaidItem.id == 3) to hit only one bank
        r = plaid_service.get_client().sandbox_item_reset_login(SandboxItemResetLoginRequest(access_token=item.access_token))
        print(item.id, item.institution_name, "reset:", r["reset_login"])
EOF
```

The app only learns about it on the next sync (pull to refresh, **Sync Now**, the daily DAG, or a webhook).

### 2.2 Plaid webhooks end to end (needs a public HTTPS URL)

Signature verification, background sync and re-login flagging are covered by tests using a locally generated key, and
the real `webhook_verification_key/get` call was exercised against the sandbox with an invalid key id. Delivery **from
Plaid** has not been seen.

1. `ngrok http 8000` and copy the `https://...` URL.
2. `backend/.env`: `PLAID_WEBHOOK_URL=https://<ngrok-host>/plaid/webhook`, then `docker compose up -d backend`.
3. In the app connect a **new** bank (existing banks were linked without a webhook URL; use *Disconnect* then connect again).
4. Fire a sandbox webhook:
   ```bash
   docker compose exec -T backend python - <<'EOF'
   from plaid.model.sandbox_item_fire_webhook_request import SandboxItemFireWebhookRequest
   from app.database import SessionLocal
   from app.models.connection import PlaidItem
   from app.services import plaid_service
   with SessionLocal() as db:
       item = db.query(PlaidItem).order_by(PlaidItem.id.desc()).first()
       r = plaid_service.get_client().sandbox_item_fire_webhook(
           SandboxItemFireWebhookRequest(access_token=item.access_token, webhook_code="SYNC_UPDATES_AVAILABLE"))
       print(r["webhook_fired"])
   EOF
   ```
5. Expect in `docker compose logs backend`: a `POST /plaid/webhook ... 200`, no "Rejected webhook" line, and Settings
   showing "Synced just now". Also open `http://127.0.0.1:4040` (ngrok inspector) and confirm the request had a
   `Plaid-Verification` header.
6. Negative check: `curl -i -X POST https://<ngrok-host>/plaid/webhook -d '{}'` gives **401**.

### 2.3 Physical Android device

1. USB debugging on; `adb devices` lists the phone; `npx expo run:android --device`.
2. `mobile/.env`: `EXPO_PUBLIC_API_URL=http://<your-LAN-ip>:8000`; the phone and computer are on the same Wi-Fi and the
   firewall allows port 8000.
3. Repeat section 1 steps 1, 3, 5, 6, 9, 22. Also check: keyboard never covers the sign-in button, status bar and
   gesture bar do not overlap content, rotate the phone on each tab, and set *Font size* to the largest in system
   settings (long names must truncate, not overflow).

### 2.4 Bank OAuth on Android (Chase and other big banks)

1. Plaid dashboard, *Developers, API, Allowed Android package names*: add `com.rosaiju.digitallifeauditor`.
2. `backend/.env`: `PLAID_ANDROID_PACKAGE_NAME=com.rosaiju.digitallifeauditor`, restart the backend.
3. Connect, search **Chase**, complete the OAuth page in the browser. *Expected:* returns to the app and shows "Connected!".
   *Failure signature:* the browser ends on "close this page and continue" and the app never gets the connection.

### 2.5 iOS

Never built. Needs macOS and Xcode: `npx expo run:ios`, then repeat section 1. Watch for keyboard and safe-area behavior
(the login screen uses `KeyboardAvoidingView` with `padding` on iOS only).

### 2.6 AI insights with the real model

1. `GROQ_API_KEY` set in `backend/.env`; `GROQ_MODEL` is `openai/gpt-oss-120b` unless Groq retired it.
2. Insights, **Generate**. *Expected footer:* "AI-written". If it says "rule-based analysis", check
   `docker compose logs backend` for `model_not_found` and pick a model from `Groq(...).models.list()`.
3. Numbers (per month, per year, category totals) must equal the Subscriptions tab: they are computed in code.

### 2.7 Airflow

1. `http://localhost:8080` (admin / admin), unpause **sync_transactions**, **Trigger DAG**.
2. Every task green; log line `[DLA] Daily sync: N Plaid items refreshed, 0 failed.`; Settings shows "Synced just now".
3. With the wrong `AIRFLOW_SYNC_SECRET` the task must fail with a 403.

### 2.8 Session expiry

Set `ACCESS_TOKEN_EXPIRE_MINUTES=1` in `backend/.env`, restart, sign in, wait 2 minutes, pull to refresh.
*Expected:* back on the sign-in screen with no stale data. Restore the value (default 10080) afterwards.

### 2.9 Screen reader

TalkBack on: every button announces a meaningful name (dismiss buttons read "Dismiss Netflix", the cancellation link
"Open cancellation page for Netflix", the ended section "Ended subscriptions, 1" with expanded/collapsed state),
banners announce as alerts, and the form error text is read after a failed submit.

### 2.10 Plaid sandbox scenarios not tried

Institutions that require MFA (Plaid docs list sandbox test institutions) and pending-to-posted transaction
transitions. Expected: MFA completes inside Link with no app-side change; pending charges never create a duplicate
subscription (Plaid removes the pending entry when it posts).
