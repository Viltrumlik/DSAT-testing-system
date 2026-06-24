# DSAT Exam Runner

A standalone, full-stack copy of the **SAT exam runner ("testing simulation")** and its
**practice-test authoring builder**, extracted from the `DSAT-mock-exam` monorepo.

- **Frontend** — Next.js 16 / React 19 (the `testing-simulation` exam runner + the
  practice-test / mock-exam builder).
- **Backend** — Django + DRF (the `exams` app and the auth/access apps it needs).

The student plays exams at `/exam/[attemptId]`; staff author the tests at
`/builder/practice-tests` and `/builder/mock-exams`. The backend owns the timer, state
machine, and scoring; the client renders truth and submits intent.

> Scope: practice-test authoring only. The monorepo's question bank, pastpapers,
> vocabulary, assessments, classes, and teacher console are **not** included as HTTP
> surfaces. Those Django apps remain installed (the `exams` model graph and migrations
> depend on them) but expose no API.

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
cp .env.example .env.local       # API_PROXY_TARGET defaults to http://localhost:8000
npm run dev                      # http://localhost:3000
```

The frontend calls a relative `/api` base; in dev, `next.config.ts` proxies `/api/*` to
`API_PROXY_TARGET`. Run **both** servers together.

## Verify end-to-end

1. Log in at `/login` as the superuser.
2. `/builder/practice-tests` → create a test → add a module → add questions.
3. Start an attempt (via the `/practice-tests` page) → `/exam/<attemptId>`.
4. Run a module, use the tools (calculator / highlight / notes), submit both modules →
   the attempt scores inline → `COMPLETED`.

## Tests

```bash
cd frontend && npm run test     # 98 unit tests (exam engine + tools)
```
