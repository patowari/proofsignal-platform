# Python / backend rules

Python **3.12** (not 3.13 — ctranslate2/faster-whisper wheels lag). Venv at
`backend/.venv`. FastAPI + Pydantic v2 + SQLAlchemy 2.0 (typed, `Mapped[...]`) +
Alembic. Ruff for lint+format, mypy for types.

## Layering

`api/` -> `services/` -> `db/`. Route handlers stay thin: validate, delegate, map
to a response schema. Domain logic belongs in `services/`, `verification/`,
`retrieval/`, `media/`. Never put a DB query in a route handler, and never let a
SQLAlchemy model instance escape into a response — always go through a Pydantic
schema in `schemas/`.

## Async

Route handlers and I/O (HTTP, DB) are async. CPU-bound and blocking library work
(sentence-transformers, OpenCV, Pillow, OCR, ffmpeg) runs in a thread via
`anyio.to_thread.run_sync` — never block the event loop. Subprocesses use
`asyncio.create_subprocess_exec` (argv list, never a shell string) with a timeout.

## Optional heavy dependencies

torch, sentence-transformers, faster-whisper, and OCR engines are **optional**.
Import them lazily inside the provider that needs them, never at module import
time. Every such provider exposes `is_available()` and a documented degraded
behavior. The app must import, boot, and serve with none of them installed —
this is enforced by the default test suite.

## Providers

`LLMProvider`, `EmbeddingProvider`, `EvidenceClassifier`, `RetrievalProvider`,
`OCREngine`, `TranscriptionProvider`, `ObjectStorage`, `SocialContentResolver`
are protocols. Concrete implementations are selected by config; never reference a
concrete provider or a hardcoded model name from domain code. Model names always
come from settings.

## Config

All settings in `app/core/config.py` via pydantic-settings. No `os.getenv` calls
scattered through the codebase. Every new setting gets an entry in `.env.example`.

## Errors

Fail loudly and specifically. Use the typed exceptions in `app/core/errors.py`.
Never swallow an exception to make a stage appear to succeed — a failed stage is
recorded as failed with its error type. Never let an internal error become a
substantive verdict.

## Tests

Deterministic and offline by default. Markers: `integration` (needs Postgres/Redis/
MinIO via Docker), `live` (needs internet), `slow`, `heavy` (needs torch/OCR).
The bare `pytest` run must pass with no Docker, no network, and no ML extras.
