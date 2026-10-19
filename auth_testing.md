# Auth-Gated App Testing Playbook (Emergent Google Auth + Telegram + Email/Password)

> Saved from integration_playbook_expert_v2. Tell the testing agent to read this file.
> NOTE: Do not be satisfied until the auth-gated pages are tested completely.

## Session model (this app)
- Unified `user_sessions` collection: `{ session_token, telegram_id, expires_at, created_at, auth_method }`.
- Every account has a `telegram_id` (real for Telegram users, synthetic for email/Google) — used as the app data key (plans/sessions).
- Auth dependency reads `session_token` from **Authorization: Bearer** header first, then cookie.

## Step 1: Create Test User & Session (mongosh)
```
mongosh --eval "
use('test_database');
var tgid = 950000000001;
var sessionToken = 'test_session_' + Date.now();
db.users.updateOne(
  { telegram_id: tgid },
  { \$setOnInsert: { id: 'test-' + tgid, telegram_id: tgid, first_name: 'Test User', email: 'test.user@example.com', auth_provider: ['email'], created_at: new Date().toISOString(), updated_at: new Date().toISOString() } },
  { upsert: true }
);
db.user_sessions.insertOne({
  session_token: sessionToken,
  telegram_id: tgid,
  auth_method: 'email',
  expires_at: new Date(Date.now() + 7*24*60*60*1000).toISOString(),
  created_at: new Date().toISOString()
});
print('Session token: ' + sessionToken);
print('telegram_id: ' + tgid);
"
```

## Step 2: Backend API
```
curl -X GET "$BASE/api/auth/me" -H "Authorization: Bearer YOUR_SESSION_TOKEN"
curl -X POST "$BASE/api/auth/register" -H "Content-Type: application/json" -d '{"email":"a@b.com","password":"pass1234","name":"A"}'
curl -X POST "$BASE/api/auth/login" -H "Content-Type: application/json" -d '{"email":"a@b.com","password":"pass1234"}'
```

## Step 3: Browser Testing (Bearer token in localStorage)
```
await page.add_init_script("window.localStorage.setItem('twb_token','YOUR_SESSION_TOKEN')")
await page.goto("$BASE/")
```

## Checklist
- /api/auth/me returns user data for valid token (200), 401 for invalid.
- register creates user + returns token; duplicate email → 400.
- login verifies password; wrong password → 401.
- Telegram auth validates initData HMAC (invalid signature → 401).
- Google: session_id exchange creates/loads user by email, returns token.
- Protected app endpoints work with the issued token.

## Emergent Google Auth flow
- Frontend redirect: `https://auth.emergentagent.com/?redirect=<window.location.origin + '/'>`
- Returns `#session_id=...` → frontend POSTs to `/api/auth/google/session` → backend GET `https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data` with header `X-Session-ID`.
- REMINDER: DO NOT HARDCODE THE REDIRECT URL OR ADD FALLBACKS — this breaks the auth.

## Test identities → save to /app/memory/test_credentials.md
- Email test account(s) + password, synthetic telegram_id, any Google test email.
