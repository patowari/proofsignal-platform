"""Application configuration.

Single source of settings. Never call os.getenv elsewhere -- add a field here and
a line to .env.example instead.

Every default is chosen so the app boots and serves with no .env file at all,
degrading rather than crashing when optional services are absent.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Application ----------------------------------------------------
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api"
    frontend_url: str = "http://localhost:3100"
    api_url: str = "http://localhost:8123"
    #: Allowed browser origins. localhost and 127.0.0.1 are distinct origins to
    #: a browser even though they resolve to the same host, so both forms of
    #: each dev port are listed -- otherwise the frontend works at one and is
    #: blocked at the other. Production sets this explicitly via env.
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3100",
            "http://127.0.0.1:3100",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"

    # ---- Datastores -----------------------------------------------------
    database_url: str = "postgresql+psycopg://verifier:verifier@localhost:55432/verifier"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    redis_url: str = "redis://localhost:56379/0"

    # ---- Object storage (MinIO / S3-compatible) -------------------------
    minio_endpoint: str = "http://localhost:59000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"  # noqa: S105 - local dev default, overridden in every real deployment
    minio_bucket: str = "verifier-media"
    minio_region: str = "us-east-1"
    minio_secure: bool = False

    # ---- Local AI -------------------------------------------------------
    # Model names are configuration, never hardcoded in domain code.
    ollama_base_url: str = "http://localhost:11434"
    ollama_text_model: str = "llama3.2:3b"
    ollama_vision_model: str = "llama3.2-vision:11b"
    ollama_timeout_seconds: float = 120.0
    ollama_enabled: bool = True

    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dimensions: int = 384
    embedding_enabled: bool = True

    nli_model: str = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
    nli_enabled: bool = True

    # ---- Groq (optional, hosted) ----------------------------------------
    # Off unless a key is set. The project must run with zero keys, so the
    # no-key path stays the default and is what the test suite exercises.
    # Submitted text leaves the machine when this is on -- that is the tradeoff
    # for much better multilingual claim and evidence understanding.
    groq_enabled: bool = False
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"
    groq_timeout_seconds: float = 45.0

    # ---- Media tooling --------------------------------------------------
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    ocr_engine: Literal["tesseract", "paddle", "none"] = "tesseract"
    tesseract_path: str = "tesseract"
    ocr_languages: str = "eng+ben"
    whisper_model: str = "base"
    whisper_enabled: bool = True

    # ---- Upload and media limits ----------------------------------------
    max_image_bytes: int = 15 * 1024 * 1024
    max_video_bytes: int = 200 * 1024 * 1024
    max_video_duration_seconds: int = 600
    max_video_resolution: int = 1920
    max_keyframes: int = 24
    max_transcript_chars: int = 50_000
    max_image_pixels: int = 50_000_000
    max_image_dimension: int = 12_000
    max_text_chars: int = 50_000

    # ---- Safe fetch / SSRF ----------------------------------------------
    max_url_response_bytes: int = 10 * 1024 * 1024
    fetch_timeout_seconds: float = 20.0
    fetch_connect_timeout_seconds: float = 8.0
    max_redirects: int = 5
    allowed_url_ports: list[int] = Field(default_factory=lambda: [80, 443])
    user_agent: str = "VerifierBot/1.0 (+https://example.org/about-our-bot)"

    # ---- Rate limits (per client fingerprint, per window) ---------------
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 3600
    rate_limit_text_submissions: int = 20
    rate_limit_url_submissions: int = 20
    rate_limit_image_submissions: int = 10
    rate_limit_video_submissions: int = 3
    rate_limit_status_polls: int = 1200
    rate_limit_search: int = 120
    #: Salt for hashing client fingerprints. Raw IPs are never stored.
    client_fingerprint_salt: str = "change-me-in-production"

    # ---- Pipeline / worker ----------------------------------------------
    queue_name: str = "verification"
    #: How long a worker blocks waiting for a job. The Redis socket timeout is
    #: derived from this, so raising it here cannot strand a worker.
    queue_block_timeout_seconds: int = 5
    worker_concurrency: int = 2
    job_max_retries: int = 3
    job_timeout_seconds: int = 900
    stage_timeout_seconds: int = 300
    max_claims_per_verification: int = 25
    max_evidence_per_claim: int = 12
    max_documents_per_claim: int = 20

    # ---- Retrieval ------------------------------------------------------
    gdelt_enabled: bool = True
    gdelt_base_url: str = "https://api.gdeltproject.org/api/v2/doc/doc"
    gdelt_timeout_seconds: float = 15.0
    gdelt_max_records: int = 50
    rss_enabled: bool = True
    feeds_config_path: str = "../infrastructure/feeds.yaml"
    rss_ingest_interval_seconds: int = 900
    retrieval_candidate_limit: int = 40
    #: Per-feed fetch timeout. Kept short: a slow publisher must not hold up a
    #: verification, and feeds are fetched concurrently anyway.
    rss_feed_timeout_seconds: float = 8.0
    #: Cap on feeds queried per verification, bounding worst-case latency.
    rss_max_feeds_per_query: int = 20
    #: Minimum retrieval score for a candidate to become evidence. Tuned against
    #: live Bangla feeds: genuinely relevant articles scored around 0.16, so a
    #: higher cut silently discarded real evidence. The discriminating-term rule
    #: in retrieval/scoring.py is what keeps coincidental matches out, not this.
    retrieval_min_score: float = 0.12
    #: Article bodies fetched per verification. Each is a full HTTP round trip
    #: through the SSRF-safe fetcher, so this bounds latency directly.
    max_article_fetches: int = 6

    @field_validator("cors_origins", "allowed_url_ports", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept comma-separated env values as well as JSON lists."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return value
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("debug", mode="before")
    @classmethod
    def _parse_debug_mode(cls, value: object) -> object:
        """Tolerate common host-level DEBUG modes that are not booleans.

        Windows developer tools sometimes export ``DEBUG=release`` globally.
        Environment variables override the project's ``.env``, so treating a
        release/production mode as false prevents an unrelated host setting
        from stopping the API and worker at startup.
        """
        if isinstance(value, str) and value.strip().lower() in {
            "release",
            "production",
            "prod",
            "off",
        }:
            return False
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def sync_database_url(self) -> str:
        """Alembic and the worker use the sync driver."""
        return self.database_url.replace("+asyncpg", "+psycopg")


@lru_cache
def get_settings() -> Settings:
    return Settings()
