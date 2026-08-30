# Running and testing this project

Everything below was executed on the development machine. Ports are
deliberately non-default because 5432, 6379, 9000, and 8000 were already taken
by other stacks.

| Service | Port | Why this port |
|---|---|---|
| PostgreSQL + pgvector | **55432** | 5432 taken by another project |
| Redis | **56379** | 6379 taken |
| MinIO API / console | **59000** / 59001 | 9000 taken |
| Backend API | **8123** | 8000 taken |
| Frontend | **3100** | 3000 taken |

---

## One-time setup

You need **Docker Desktop**, **Python 3.12**, **Node 20+**, and **pnpm**.

```bash
# 1. Backend virtualenv  (from repo root)
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"

# 2. Frontend dependencies
cd ../apps/web
pnpm install

# 3. Environment file  (from repo root)
cd ../..
cp .env.example .env
```

The defaults in `.env.example` already point at the ports above, so no editing
is needed for local use.

---

## Start everything

Open **four terminals**. All paths are from the repository root.

### Terminal 1 — infrastructure

```bash
docker compose up -d
docker compose ps          # all three should read "healthy"
```

First run only, to create the tables:

```bash
cd backend
.venv/Scripts/python -m alembic upgrade head
```

### Terminal 2 — API server

```bash
cd backend
.venv/Scripts/python run_api.py --port 8123
```

Use `run_api.py`, **not** `uvicorn app.main:app`. On Windows, psycopg's async
driver cannot run on the default ProactorEventLoop and every database query
fails with `InterfaceError`; this entrypoint installs a compatible loop first.

### Terminal 3 — verification worker

```bash
cd backend
.venv/Scripts/python -m app.workers.worker
```

**Without this, submissions stay QUEUED forever.** The API only enqueues work;
the worker performs it.

### Terminal 4 — frontend

```bash
cd apps/web
pnpm dev --port 3100
```

Then open **http://localhost:3100**.

---

## Try it in the browser

1. Go to http://localhost:3100
2. Paste something with checkable facts, e.g.

   > A 7.8 magnitude earthquake hit Japan today, killing 500 people and causing a tsunami. The government approved $50 billion in emergency aid.

3. Press **Verify**. You land on `/verify/vfy_…` and watch the real stages
   advance — each line is a database row written by the worker, not an
   animation.
4. When it finishes, the same page becomes the report.

Other pages: **/method** (what the verdicts mean and what we cannot do),
**/recent** (all public verifications).

### What you should expect to see

Every verification currently comes back **UNVERIFIED** with **Low confidence**,
and the report says so explicitly:

> Evidence retrieval is not yet available in this build, so no sources were
> searched. This result means the claims are unverified — it does not mean they
> are false.

That is correct, not a bug. Retrieval (RSS, GDELT, hybrid search) is the next
phase. Until it exists there is genuinely no evidence, and the honest verdict
for a claim nobody has checked is UNVERIFIED. The system never invents evidence
to look more capable than it is.

What *does* work end to end today: submission of all four content types, upload
validation, SSRF protection, rate limiting, atomic claim extraction in English
and Bangla, the full job queue with retries and crash recovery, all twelve
pipeline stages persisting real transitions, deterministic scoring, and the
complete report UI.

---

## Testing with Postman

Import both files from `postman/`:

- `Evidence-Verification-API.postman_collection.json` — 21 requests
- `Local.postman_environment.json` — the base URL

Select the **Evidence Verification — Local** environment, then:

1. Run **Health → GET /api/ready**. Required dependencies should be `ok`;
   Ollama and Tesseract show `unavailable`, which is expected on a machine
   without them and reports as `degraded`, not an outage.
2. Run **Submissions → POST /api/submissions/text**. It returns `202` and
   automatically saves `verificationId` to a collection variable.
3. Run **Verifications → GET /status** a few times. Watch the stages advance in
   the Postman console (View → Show Postman Console).
4. Run **Verifications → GET /verifications/{id}** for the full report.
5. Run the whole **Security checks** folder. Every request there is *supposed*
   to be rejected — each one asserts a protection is working:
   - SSRF against loopback, cloud metadata, private ranges, obfuscated IPs
     (`http://2130706433/` is decimal for 127.0.0.1), `file://`, and internal
     ports
   - Validation and id-shape rejection

For image and video uploads you must select a file in the request's **Body**
tab first — Postman cannot store a file path in a shared collection.

### Command line, if you prefer

```bash
# Submit and capture the id
curl -s -X POST http://127.0.0.1:8123/api/submissions/text \
  -H 'Content-Type: application/json' \
  -d '{"text":"A 7.8 magnitude earthquake hit Japan today, killing 500 people."}'

# Poll status  (substitute the id from above)
curl -s http://127.0.0.1:8123/api/verifications/vfy_XXXX/status

# Full report
curl -s http://127.0.0.1:8123/api/verifications/vfy_XXXX
```

Interactive API docs: **http://127.0.0.1:8123/api/docs**

---

## Running the test suites

```bash
# Backend  (from backend/)  — 321 tests, no Docker or network needed
.venv/Scripts/python -m pytest

# Integration  — needs docker compose up
.venv/Scripts/python -m pytest -m integration

# Lint and types
.venv/Scripts/python -m ruff check . && .venv/Scripts/python -m mypy app

# Frontend  (from apps/web/)
pnpm typecheck
pnpm build
```

---

## Inspecting the data directly

```bash
# What has been submitted and what came of it
docker exec verifier-postgres psql -U verifier -d verifier \
  -c "SELECT public_id, status, overall_verdict, current_stage FROM verifications ORDER BY id DESC LIMIT 10;"

# Real stage transitions for one verification
docker exec verifier-postgres psql -U verifier -d verifier \
  -c "SELECT sequence, stage, status, duration_ms FROM verification_stages ORDER BY id DESC LIMIT 12;"

# Queue depth and dead-lettered jobs
docker exec verifier-redis redis-cli LLEN queue:verification:pending
docker exec verifier-redis redis-cli LLEN queue:verification:dead

# Uploaded media  (MinIO console, login minioadmin / minioadmin)
open http://localhost:59001
```

---

## Troubleshooting

**Submissions stay QUEUED.** The worker is not running — start Terminal 3.
Check the queue with `docker exec verifier-redis redis-cli LLEN
queue:verification:pending`; a growing number confirms it.

**`InterfaceError` on every database call.** You started the API with `uvicorn`
directly. Use `python run_api.py` — see Terminal 2 above.

**Port already allocated on `docker compose up`.** Another stack has that port.
Edit the host side of the mapping in `docker-compose.yml` and update
`DATABASE_URL` / `REDIS_URL` / `MINIO_ENDPOINT` in `.env` to match.

**Frontend shows "The verification service is not responding."** The API is not
running on 8123, or `NEXT_PUBLIC_API_URL` in `apps/web/.env.local` points
somewhere else.

**`/api/ready` reports `degraded`.** Expected without Ollama and Tesseract. Both
are optional: claim extraction falls back to rules, and OCR is skipped and
reported as unavailable rather than as "no text found".

**Docker daemon not reachable.** Start Docker Desktop and wait for the engine —
`docker version` should print a Server section.
