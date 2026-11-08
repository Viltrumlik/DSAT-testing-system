# DSAT Exam Runner

A standalone, full-stack copy of the **Digital SAT exam runner ("testing simulation")** and its
**practice-test authoring builder**, extracted from the
[`DSAT-mock-exam`](https://github.com/Viltrumlik/DSAT-mock-exam) monorepo.

- **Frontend** — Next.js 16 / React 19 (the `testing-simulation` exam runner + the
  practice-test / mock-exam builder).
- **Backend** — Django 6 + Django REST Framework (the `exams` app and the auth/access apps it needs).

The student plays exams at `/exam/[attemptId]`; staff author the tests at
`/builder/practice-tests` and `/builder/mock-exams`. The backend owns the timer, state
machine, and scoring; the client renders truth and submits intent.

> Scope: practice-test authoring only. The monorepo's question bank, pastpapers,
> vocabulary, assessments, classes, and teacher console are **not** included as HTTP
> surfaces. Those Django apps remain installed (the `exams` model graph and migrations
> depend on them) but expose no API.

## Features

- **Exam runner** — server-clock module timer, attempt state machine, autosave with local
  drafts, module transitions, a "check your work" review page, question navigator, and
  student-produced response (SPR) input.
- **In-exam tools** — Desmos graphing calculator (falls back to a built-in scientific
  calculator), text highlighting and annotations, a notes panel, the SAT reference sheet,
  keyboard shortcuts, a full-screen warning, and a multi-tab guard.
- **Math rendering** — KaTeX for formulas in passages, questions, and options.
- **Builder** — create practice-test packs, practice tests, and mock exams; add modules and
  questions (including question and option images).
- **Scoring** — attempts are scored by the backend: inline in local mode, or by a Celery
  worker when a broker is configured.
- **Auth** — JWT in cookies (login / refresh / logout, session list and revoke),
  self-registration, optional Google and Telegram sign-in.
- **Ops** — health endpoints (`/api/health/live/`, `/api/health/ready/`) and an OpenAPI
  schema with Swagger UI.

## Tech stack

| Layer    | Technologies |
|----------|--------------|
| Backend  | Python 3.12+, Django 6.0, DRF, SimpleJWT, drf-spectacular, Celery + Redis (optional), PostgreSQL (production) / SQLite (local), WhiteNoise, Jazzmin admin |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, TanStack Query, Zustand, React Hook Form + Zod, Axios, KaTeX, Recharts |
| Tests    | Vitest (frontend unit tests) |

## Requirements

- Python 3.12+
- Node 20+ / npm

## Backend — run

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then set SECRET_KEY (python -c "import secrets;print(secrets.token_urlsafe(50))")
python manage.py migrate
python manage.py createsuperuser   # use a super_admin to author in the builder
python manage.py runserver 0.0.0.0:8000
```

`DEBUG=True` (the default in `.env.example`) runs everything single-process: SQLite,
in-memory cache, and **inline exam scoring** — no Postgres, Redis, or Celery needed.

## Frontend — run

```bash
cd frontend
npm install
cp .env.example .env.local       # sets API_PROXY_TARGET=http://localhost:8000
npm run dev                      # http://localhost:3000
```

The frontend calls a relative `/api` base; in dev, `next.config.ts` proxies `/api/*` to
`API_PROXY_TARGET`. Run **both** servers together.

> If `API_PROXY_TARGET` is not set, the dev proxy falls back to the production API
> (`https://mastersat.uz`). Keep it pointed at your local backend while developing.

## Configuration

Backend (`backend/.env`, loaded automatically by `config/settings.py`):

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Django secret key (required). |
| `DEBUG` | `True` enables local single-process mode (SQLite, LocMem cache, inline scoring). |
| `ALLOWED_HOSTS` | Comma-separated host names. |
| `DATABASE_URL`, `DB_SSL` | PostgreSQL connection; leave empty for local SQLite. |
| `REDIS_URL` | Shared cache; leave empty for in-process cache. |
| `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Celery broker/backend; leave empty to score inline. |
| `EXAMS_SCORE_INLINE_IF_NO_CELERY` | Score attempts inline when no Celery worker is available. |
| `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS_EXTRA` | Frontend origins (e.g. `http://localhost:3000`). |
| `GOOGLE_CLIENT_ID` | Optional Google sign-in. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` | Optional Telegram sign-in. |

Frontend (`frontend/.env.local`):

| Variable | Purpose |
|----------|---------|
| `API_PROXY_TARGET` | Backend URL used by the dev `/api` proxy. |
| `NEXT_PUBLIC_API_URL` | Optional absolute API URL (bypasses the proxy; requires CORS). |
| `NEXT_PUBLIC_DESMOS_API_KEY` | Optional Desmos API key for the graphing calculator. |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | Optional Google sign-in (must match the backend). |

## Verify end-to-end

1. Log in at `/login` as the superuser.
2. `/builder/practice-tests` → create a test → add a module → add questions.
3. Start an attempt (via the `/practice-tests` page) → `/exam/<attemptId>`.
4. Run a module, use the tools (calculator / highlight / notes), submit both modules →
   the attempt scores inline → `COMPLETED`.

## API

- OpenAPI schema: `GET /api/schema/`
- Swagger UI: `/api/schema/swagger/`
- Django admin: `/django-admin/`

Main route groups: `/api/auth/`, `/api/users/`, `/api/exams/`, `/api/access/`.

## Tests

```bash
cd frontend && npm run test     # 98 unit tests (exam engine + tools)
```

## Project structure

```
DSAT-testing-system/
├── backend/
│   ├── config/          # Django settings, URLs, Celery, health, security middleware
│   ├── exams/           # Practice tests, mock exams, modules, questions, attempts, scoring
│   ├── users/           # Custom user, cookie JWT auth, Google / Telegram sign-in
│   ├── access/          # Roles, permissions, access grants
│   ├── core/            # Shared primitives (errors, idempotency, events, metrics)
│   ├── assessments/ classes/ questionbank/ realtime/ vocabulary/
│   │                    # Installed for the model graph only — no HTTP routes
│   ├── openapi.yaml
│   └── requirements.txt
└── frontend/
    ├── src/app/                         # Routes: /exam, /builder, /practice-tests, /login, /register
    ├── src/features/testing-simulation/ # Exam runner: components, hooks, tools, state
    ├── src/features/examsAdmin/         # Builder API
    ├── src/components/                  # Shell, UI kit, charts
    └── src/lib/                         # API client, auth, math rendering, permissions
```

## License

Released under the [MIT License](LICENSE).
