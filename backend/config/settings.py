"""
Django settings for MockExam production project.
Reads all configuration from environment variables.
"""

import os
import sys
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file (dev) or system environment variables (prod)
load_dotenv(os.path.join(BASE_DIR, '.env'))


# ─── Security ────────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set!")

DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'


def _env_bool(name: str, *, default_when_unset: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default_when_unset
    return v.lower() == 'true'


# access.services — fail loud in dev (override with env in CI/prod)
LMS_AUTHZ_RAISE_ON_MISSING_SUBJECT = _env_bool(
    'LMS_AUTHZ_RAISE_ON_MISSING_SUBJECT', default_when_unset=DEBUG
)
LMS_AUTHZ_CONSISTENCY_CHECKS = _env_bool(
    'LMS_AUTHZ_CONSISTENCY_CHECKS', default_when_unset=DEBUG
)
LMS_AUTHZ_RAISE_ON_CONSISTENCY_DRIFT = _env_bool(
    'LMS_AUTHZ_RAISE_ON_CONSISTENCY_DRIFT', default_when_unset=DEBUG
)
# Log role/subject and queryset counts around test-library filters (set True to debug prod issues).
LMS_AUTHZ_DEBUG_FILTERS = _env_bool('LMS_AUTHZ_DEBUG_FILTERS', default_when_unset=False)

# Centralized access engine (Phase 2) rollout flags — all default OFF so the new
# engine is inert in production until explicitly enabled. See docs/access-redesign/.
ACCESS_ENGINE_DUAL_WRITE = _env_bool('ACCESS_ENGINE_DUAL_WRITE', default_when_unset=False)
ACCESS_ENGINE_READ = _env_bool('ACCESS_ENGINE_READ', default_when_unset=False)
ACCESS_ENGINE_SHADOW_READ = _env_bool('ACCESS_ENGINE_SHADOW_READ', default_when_unset=False)

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
# Telegram bot HTTP API token (used for getMe to discover bot username, and as the default OIDC client_id source).
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
# Optional: bot username without @. If empty, the API may call Telegram getMe once (cached) to discover it.
TELEGRAM_BOT_USERNAME = os.getenv('TELEGRAM_BOT_USERNAME', '').strip().lstrip('@')
# Telegram OIDC (https://core.telegram.org/bots/telegram-login) confidential-client credentials.
# client_id is the bot id (digits before ":" in TELEGRAM_BOT_TOKEN) unless overridden.
TELEGRAM_OIDC_CLIENT_ID = os.getenv('TELEGRAM_OIDC_CLIENT_ID', '').strip()
TELEGRAM_OIDC_CLIENT_SECRET = os.getenv('TELEGRAM_OIDC_CLIENT_SECRET', '').strip()
# Absolute https URL registered with Telegram OIDC as redirect_uri.
TELEGRAM_OIDC_REDIRECT_URI = os.getenv(
    'TELEGRAM_OIDC_REDIRECT_URI',
    'https://mastersat.uz/api/users/telegram/callback/',
).strip()
# Synthetic email domain for users without email (must stay unique per Telegram user id).
TELEGRAM_SYNTHETIC_EMAIL_DOMAIN = os.getenv(
    'TELEGRAM_SYNTHETIC_EMAIL_DOMAIN',
    'telegram.mastersat.local',
)


# ─── Application Definition ───────────────────────────────────────────────────

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party
    'rest_framework',
    'drf_spectacular',
    'corsheaders',

    # Local apps
    'access',
    'users',
    'exams',
    'classes',
    'realtime',
    'vocabulary',
    'assessments.apps.AssessmentsConfig',
    'questionbank.apps.QuestionBankConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Serve static files efficiently
    # Trace id + request timing (safe in prod).
    'core.tracing.RequestTraceMiddleware',
    'core.tracing.RequestTimingMiddleware',
    # Canary bucketing (for edge routing).
    'core.canary.CanarySamplingMiddleware',
    # Security headers (CSP report-only by default).
    'config.security_headers.CSPMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    # Detect legacy per-subdomain csrftoken/JWT cookies left over from a DEBUG=True period.
    # Listed BEFORE CsrfViewMiddleware so it runs LAST in the response phase — Django CSRF
    # middleware first writes its csrftoken Set-Cookie with Domain=.mastersat.uz, then this
    # middleware overrides it with a no-Domain deletion only when a duplicate was detected.
    'core.cookie_cleanup.LegacyCookieCleanupMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    # Enforce CSRF for cookie-authenticated API requests (DRF APIViews are CSRF-exempt by default).
    'config.csrf_api.APICSRFEnforceMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # Populate JWT user before host-based API guards (DRF auth runs later per-view).
    'access.middleware.JWTUserMiddleware',
    'config.auth_correlation_middleware.AuthCorrelationMiddleware',
    'access.middleware.StaffSubjectRequiredMiddleware',
    # SubdomainAPIGuardMiddleware removed: the standalone exam-runner is single-host,
    # so the per-subdomain API gate (admin/questions/teacher console routing) is moot.
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# ─── Database ─────────────────────────────────────────────────────────────────
# Uses PostgreSQL in production (when DATABASE_URL is set), SQLite locally.

DATABASE_URL = os.getenv('DATABASE_URL', '')

# Local test safety: allow forcing SQLite even if DATABASE_URL points to Postgres
# (useful when psycopg isn't installed locally).
FORCE_SQLITE_FOR_TESTS = os.getenv("LMS_FORCE_SQLITE_FOR_TESTS", "").lower() in ("1", "true", "yes")
RUNNING_TESTS = any(a in ("test", "pytest") for a in sys.argv)
if RUNNING_TESTS and FORCE_SQLITE_FOR_TESTS:
    DATABASE_URL = ""

if not DEBUG and not DATABASE_URL:
    raise ValueError("DATABASE_URL must be set in production")

if DATABASE_URL:
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            ssl_require=os.getenv('DB_SSL', 'False').lower() == 'true',
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Realtime + shared cache (throttles, homework metrics, alert dedupe): set in production.
REDIS_URL = os.getenv("REDIS_URL", "").strip()

# ─── Cache ─────────────────────────────────────────────────────────────────────
# Use Redis when REDIS_URL is set so throttles and homework counters are consistent across workers.
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "unique-snowflake",
        }
    }

# Production: fail fast if Redis is not configured (LocMem breaks cross-worker throttles and metrics).
CLASSROOM_ENFORCE_REDIS_CACHE = _env_bool(
    "CLASSROOM_ENFORCE_REDIS_CACHE",
    default_when_unset=(not DEBUG),
)
# Assessments: same contract — assignment throttles + abuse counters require shared Redis in prod.
ASSESSMENT_ENFORCE_REDIS_CACHE = _env_bool(
    "ASSESSMENT_ENFORCE_REDIS_CACHE",
    default_when_unset=(not DEBUG),
)
# Homework submit counters require a shared backend; disable only for single-process local dev.
CLASSROOM_METRICS_REQUIRE_SHARED_CACHE = _env_bool(
    "CLASSROOM_METRICS_REQUIRE_SHARED_CACHE",
    default_when_unset=(not DEBUG),
)
# Suppress duplicate CRITICAL webhook/email for the same fingerprint (seconds).
CLASSROOM_ALERT_COOLDOWN_SECONDS = int(os.getenv("CLASSROOM_ALERT_COOLDOWN_SECONDS", "900"))

# Dedupe windows (seconds): longer for low priority reduces write amplification for chatty traffic.
REALTIME_DEFAULT_DEDUPE_SECONDS = int(os.getenv("REALTIME_DEFAULT_DEDUPE_SECONDS", "2"))
REALTIME_LOW_PRIORITY_DEDUPE_SECONDS = int(os.getenv("REALTIME_LOW_PRIORITY_DEDUPE_SECONDS", "5"))
# 1.0 = persist all low-priority rows; <1.0 drops some low events before outbox (no durable replay for skipped).
REALTIME_LOW_PRIORITY_DB_SAMPLE_RATE = float(os.getenv("REALTIME_LOW_PRIORITY_DB_SAMPLE_RATE", "1.0"))
REALTIME_BULK_BATCH_SIZE = int(os.getenv("REALTIME_BULK_BATCH_SIZE", "500"))

# Backpressure (self-regulating realtime) — safe defaults, tune per environment.
REALTIME_BACKPRESSURE_ENABLED = os.getenv("REALTIME_BACKPRESSURE_ENABLED", "True").lower() == "true"
REALTIME_BP_MIN_LOW_SAMPLE_RATE = float(os.getenv("REALTIME_BP_MIN_LOW_SAMPLE_RATE", "0.05"))
REALTIME_BP_MAX_LOW_DEDUPE_SECONDS = int(os.getenv("REALTIME_BP_MAX_LOW_DEDUPE_SECONDS", "20"))
REALTIME_BP_DROP_LOW_AT_CRITICAL = os.getenv("REALTIME_BP_DROP_LOW_AT_CRITICAL", "True").lower() == "true"
REALTIME_BP_DROP_MEDIUM_AT_CRITICAL = os.getenv("REALTIME_BP_DROP_MEDIUM_AT_CRITICAL", "False").lower() == "true"

# Pressure thresholds.
REALTIME_BP_PERSISTED_PER_S_ELEVATED = float(os.getenv("REALTIME_BP_PERSISTED_PER_S_ELEVATED", "80"))
REALTIME_BP_PERSISTED_PER_S_HIGH = float(os.getenv("REALTIME_BP_PERSISTED_PER_S_HIGH", "160"))
REALTIME_BP_PERSISTED_PER_S_CRITICAL = float(os.getenv("REALTIME_BP_PERSISTED_PER_S_CRITICAL", "260"))

REALTIME_BP_LATENCY_MS_ELEVATED = float(os.getenv("REALTIME_BP_LATENCY_MS_ELEVATED", "250"))
REALTIME_BP_LATENCY_MS_HIGH = float(os.getenv("REALTIME_BP_LATENCY_MS_HIGH", "600"))
REALTIME_BP_LATENCY_MS_CRITICAL = float(os.getenv("REALTIME_BP_LATENCY_MS_CRITICAL", "1200"))

REALTIME_BP_RESYNC_PER_S_ELEVATED = float(os.getenv("REALTIME_BP_RESYNC_PER_S_ELEVATED", "0.2"))
REALTIME_BP_RESYNC_PER_S_HIGH = float(os.getenv("REALTIME_BP_RESYNC_PER_S_HIGH", "0.6"))
REALTIME_BP_RESYNC_PER_S_CRITICAL = float(os.getenv("REALTIME_BP_RESYNC_PER_S_CRITICAL", "1.2"))

REALTIME_BP_REDIS_FAIL_RATIO_ELEVATED = float(os.getenv("REALTIME_BP_REDIS_FAIL_RATIO_ELEVATED", "0.02"))
REALTIME_BP_REDIS_FAIL_RATIO_HIGH = float(os.getenv("REALTIME_BP_REDIS_FAIL_RATIO_HIGH", "0.05"))
REALTIME_BP_REDIS_FAIL_RATIO_CRITICAL = float(os.getenv("REALTIME_BP_REDIS_FAIL_RATIO_CRITICAL", "0.12"))

# Alert thresholds (used by realtime.alerts + Prometheus scrape hooks; tune per environment).
REALTIME_ALERT_MAX_RESYNC_RATIO = float(os.getenv("REALTIME_ALERT_MAX_RESYNC_RATIO", "0.12"))
REALTIME_ALERT_MIN_RESYNC_EVENTS = int(os.getenv("REALTIME_ALERT_MIN_RESYNC_EVENTS", "5"))
REALTIME_ALERT_MAX_DEDUPE_SUPPRESSION_RATIO = float(os.getenv("REALTIME_ALERT_MAX_DEDUPE_SUPPRESSION_RATIO", "0.85"))
REALTIME_ALERT_MIN_DEDUPE_EVENTS = int(os.getenv("REALTIME_ALERT_MIN_DEDUPE_EVENTS", "50"))
REALTIME_ALERT_MAX_REDIS_FAILURE_RATIO = float(os.getenv("REALTIME_ALERT_MAX_REDIS_FAILURE_RATIO", "0.05"))
REALTIME_ALERT_MIN_REDIS_FAILURES = int(os.getenv("REALTIME_ALERT_MIN_REDIS_FAILURES", "3"))

# Optional: expose emit→receive traces in logs when True or DEBUG.
REALTIME_DEBUG_TRACE = os.getenv("REALTIME_DEBUG_TRACE", "False").lower() == "true"

# SSE: DB replay polling interval per connection (seconds).
REALTIME_SSE_DB_POLL_EVERY_S = float(os.getenv("REALTIME_SSE_DB_POLL_EVERY_S", "0.8"))

# SSE: max lifetime of a single stream before the server ends it cleanly and the
# browser's EventSource reconnects (seconds). MUST stay well below the gunicorn
# worker --timeout (120s): a sync worker stays inside the streaming generator for
# the whole connection, so if the stream outlives the timeout the arbiter kills
# the worker (logged as a 500) and recycles it. Ending well before that yields a
# clean 200 + graceful reconnect, and bounds how long each sync worker is tied up.
# No events are lost: they are persisted and re-fetched via last_id on reconnect.
REALTIME_SSE_MAX_STREAM_S = float(os.getenv("REALTIME_SSE_MAX_STREAM_S", "25"))

# ─── Celery (optional in dev; required for scale) ─────────────────────────────
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "")
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "False").lower() == "true"
CELERY_TASK_EAGER_PROPAGATES = True

# Exams: when Celery broker is not configured (local/dev), score inline so attempts can complete.
EXAMS_SCORE_INLINE_IF_NO_CELERY = _env_bool("EXAMS_SCORE_INLINE_IF_NO_CELERY", default_when_unset=DEBUG)
# Stored idempotency responses: floor TTL (seconds). Actual TTL also considers summed module time limits + slack.
EXAM_ATTEMPT_IDEMPOTENCY_TTL_SECONDS = int(os.getenv("EXAM_ATTEMPT_IDEMPOTENCY_TTL_SECONDS", str(24 * 60 * 60)))
# Persist ``AttemptEngineAudit`` rows for exam state transitions (debugging / forensic replay).
EXAM_ENGINE_AUDIT_DB = _env_bool("EXAM_ENGINE_AUDIT_DB", default_when_unset=True)
# Exam ``Question.order`` is dense (0..n-1) under a per-module lock — see ``exams.question_ordering``.
# If True, ``post_delete`` on questions compacts the module (O(n); default off).
EXAM_QUESTION_COMPACT_ON_DELETE = _env_bool("EXAM_QUESTION_COMPACT_ON_DELETE", default_when_unset=False)

# Deadlock / serialization retries for classroom submission transactions.
CLASSROOM_DB_DEADLOCK_MAX_ATTEMPTS = int(os.getenv("CLASSROOM_DB_DEADLOCK_MAX_ATTEMPTS", "4"))
# Log CRITICAL when a StaleStorageBlob row fails this many times in a row.
CLASSROOM_STALE_STORAGE_ALERT_AFTER = int(os.getenv("CLASSROOM_STALE_STORAGE_ALERT_AFTER", "8"))

# Celery Beat (optional): stale homework file cleanup. Requires celery-beat and broker.
CELERY_BEAT_SCHEDULE = {
    "cleanup-stale-homework-storage": {
        "task": "classes.tasks.cleanup_stale_homework_storage",
        "schedule": crontab(minute="*/15"),
    },
    "prune-homework-staged-uploads": {
        "task": "classes.tasks.prune_homework_staged_uploads",
        "schedule": crontab(hour=3, minute=15),
    },
    "assessments-abandon-inactive-attempts": {
        "task": "assessments.tasks.abandon_inactive_attempts",
        "schedule": crontab(minute="*/10"),
    },
    "assessments-prune-audit-events": {
        "task": "assessments.tasks.prune_assessment_audit_events",
        "schedule": crontab(hour=4, minute=10),
    },
    "assessments-dispatch-pending-grading": {
        "task": "assessments.tasks.dispatch_pending_grading",
        "schedule": crontab(minute="*/1"),
    },
    "assessments-alert-on-slo": {
        "task": "assessments.tasks.alert_on_assessment_slo",
        "schedule": crontab(minute="*/5"),
    },
    "assessments-homework-abuse-db": {
        "task": "assessments.tasks.alert_homework_assignment_abuse_db",
        "schedule": crontab(minute="*/5"),
    },
    "assessments-prune-security-alerts": {
        "task": "assessments.tasks.prune_security_alerts",
        "schedule": crontab(hour=4, minute=40),
    },
}

# Vocabulary SRS queue caps for GET /api/vocab/today/ (query params cannot exceed these).
_VOCAB_MAX_NEW_PER_DAY = int(os.getenv("VOCAB_MAX_NEW_PER_DAY", "10"))
VOCAB_MAX_NEW_PER_DAY = max(0, _VOCAB_MAX_NEW_PER_DAY)
_VOCAB_MAX_REVIEW_PER_DAY = int(os.getenv("VOCAB_MAX_REVIEW_PER_DAY", "50"))
VOCAB_MAX_REVIEW_PER_DAY = max(0, _VOCAB_MAX_REVIEW_PER_DAY)

# Assessments: attempt inactivity timeout (seconds) before auto-abandon.
ASSESSMENT_ATTEMPT_INACTIVITY_TIMEOUT_SECONDS = int(
    os.getenv("ASSESSMENT_ATTEMPT_INACTIVITY_TIMEOUT_SECONDS", "3600")
)

# Assessments: require an answer for every question before submit.
ASSESSMENT_ENFORCE_COMPLETENESS = os.getenv("ASSESSMENT_ENFORCE_COMPLETENESS", "False").lower() == "true"

# Assessments: active time tracking (seconds). We only count time between server-observed events,
# capped per interaction and ignored after idle gaps.
ASSESSMENT_ACTIVE_IDLE_THRESHOLD_SECONDS = int(os.getenv("ASSESSMENT_ACTIVE_IDLE_THRESHOLD_SECONDS", "90"))
ASSESSMENT_ACTIVE_SLICE_CAP_SECONDS = int(os.getenv("ASSESSMENT_ACTIVE_SLICE_CAP_SECONDS", "45"))

# Assessments: maximum lifetime for an attempt (seconds) before rejecting writes/submission.
ASSESSMENT_MAX_ATTEMPT_LIFETIME_SECONDS = int(os.getenv("ASSESSMENT_MAX_ATTEMPT_LIFETIME_SECONDS", str(6 * 60 * 60)))

# Assessments: grading retry policy (Celery).
ASSESSMENT_GRADING_MAX_RETRIES = int(os.getenv("ASSESSMENT_GRADING_MAX_RETRIES", "3"))
ASSESSMENT_GRADING_RETRY_COUNTDOWN_SECONDS = int(os.getenv("ASSESSMENT_GRADING_RETRY_COUNTDOWN_SECONDS", "10"))

# Assessments: backpressure and dispatcher.
ASSESSMENT_GRADING_MAX_INFLIGHT = int(os.getenv("ASSESSMENT_GRADING_MAX_INFLIGHT", "500"))
ASSESSMENT_GRADING_DISPATCH_BATCH = int(os.getenv("ASSESSMENT_GRADING_DISPATCH_BATCH", "50"))
ASSESSMENT_GRADING_MAX_ENQUEUE_PER_MINUTE = int(os.getenv("ASSESSMENT_GRADING_MAX_ENQUEUE_PER_MINUTE", "2000"))

# Assessments: admin safety rails.
ASSESSMENT_ADMIN_REQUEUE_COOLDOWN_SECONDS = int(os.getenv("ASSESSMENT_ADMIN_REQUEUE_COOLDOWN_SECONDS", "60"))
ASSESSMENT_ADMIN_REQUEUE_MAX_PER_ATTEMPT = int(os.getenv("ASSESSMENT_ADMIN_REQUEUE_MAX_PER_ATTEMPT", "6"))

# Assessments: ops alerting (optional). If unset, falls back to CLASSROOM_OPS_WEBHOOK_URL.
ASSESSMENT_OPS_WEBHOOK_URL = os.getenv("ASSESSMENT_OPS_WEBHOOK_URL", "").strip()

# Assessments: alert thresholds (SLO-based defaults).
ASSESSMENT_ALERT_P90_LATENCY_SECONDS = float(os.getenv("ASSESSMENT_ALERT_P90_LATENCY_SECONDS", "30"))
ASSESSMENT_ALERT_FAILURE_RATE_PCT = float(os.getenv("ASSESSMENT_ALERT_FAILURE_RATE_PCT", "0.5"))
ASSESSMENT_ALERT_PENDING_OLDER_THAN_SECONDS = int(os.getenv("ASSESSMENT_ALERT_PENDING_OLDER_THAN_SECONDS", "600"))
ASSESSMENT_ALERT_PENDING_OLDER_THAN_COUNT = int(os.getenv("ASSESSMENT_ALERT_PENDING_OLDER_THAN_COUNT", "200"))

# Homework assignment abuse detection (cache buckets + optional DB backstop).
ASSESSMENT_HW_ABUSE_WINDOW_SECONDS = int(os.getenv("ASSESSMENT_HW_ABUSE_WINDOW_SECONDS", "300"))
ASSESSMENT_HW_ABUSE_ALERT_USER_COUNT = int(os.getenv("ASSESSMENT_HW_ABUSE_ALERT_USER_COUNT", "25"))
ASSESSMENT_HW_ABUSE_ALERT_CLASS_COUNT = int(os.getenv("ASSESSMENT_HW_ABUSE_ALERT_CLASS_COUNT", "80"))
ASSESSMENT_HW_ABUSE_ALERT_GLOBAL_COUNT = int(os.getenv("ASSESSMENT_HW_ABUSE_ALERT_GLOBAL_COUNT", "400"))
ASSESSMENT_HW_ABUSE_DB_LOOKBACK_MINUTES = int(os.getenv("ASSESSMENT_HW_ABUSE_DB_LOOKBACK_MINUTES", "5"))
ASSESSMENT_HW_ABUSE_DB_GLOBAL_THRESHOLD = int(os.getenv("ASSESSMENT_HW_ABUSE_DB_GLOBAL_THRESHOLD", "500"))

# Optional auto-mitigation when sliding-window abuse thresholds fire (requires shared Redis cache).
ASSESSMENT_HW_AUTO_MITIGATE = _env_bool("ASSESSMENT_HW_AUTO_MITIGATE", default_when_unset=False)
ASSESSMENT_HW_MITIGATE_USER_BLOCK_SECONDS = int(os.getenv("ASSESSMENT_HW_MITIGATE_USER_BLOCK_SECONDS", "900"))
ASSESSMENT_HW_MITIGATE_CLASS_STRICT_SECONDS = int(os.getenv("ASSESSMENT_HW_MITIGATE_CLASS_STRICT_SECONDS", "1800"))
ASSESSMENT_HW_MITIGATE_GLOBAL_COOLDOWN_SECONDS = int(os.getenv("ASSESSMENT_HW_MITIGATE_GLOBAL_COOLDOWN_SECONDS", "120"))
ASSESSMENT_HW_MITIGATE_GLOBAL_BLOCK_ASSIGN = _env_bool(
    "ASSESSMENT_HW_MITIGATE_GLOBAL_BLOCK_ASSIGN",
    default_when_unset=False,
)

# Sliding-window Redis ZSET memory cap (events per key).
ASSESSMENT_SW_ZSET_MAX_EVENTS = int(os.getenv("ASSESSMENT_SW_ZSET_MAX_EVENTS", "5000"))

# SecurityAlert retention (days).
ASSESSMENT_SECURITY_ALERT_RETENTION_DAYS = int(os.getenv("ASSESSMENT_SECURITY_ALERT_RETENTION_DAYS", "180"))

# Assessments: audit retention (days). Old rows are pruned by a periodic task (or cron).
ASSESSMENT_AUDIT_RETENTION_DAYS = int(os.getenv("ASSESSMENT_AUDIT_RETENTION_DAYS", "180"))


# ─── Password Validation ──────────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ─── Internationalisation ─────────────────────────────────────────────────────

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True


# ─── Static & Media Files ─────────────────────────────────────────────────────

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# WhiteNoise compression & caching
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# ─── Auth & JWT ───────────────────────────────────────────────────────────────

AUTH_USER_MODEL = 'users.User'

AUTHENTICATION_BACKENDS = [
    'users.backends.EmailOrUsernameModelBackend',
    'django.contrib.auth.backends.ModelBackend',
]

SIMPLE_JWT = {
    # Short-lived access; browser uses refresh cookie to renew.
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=3),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'AUTH_HEADER_TYPES': ('Bearer',),
}


# ─── CORS ─────────────────────────────────────────────────────────────────────

CORS_ALLOW_ALL_ORIGINS = DEBUG  # Only allow all in debug mode
CORS_ALLOWED_ORIGINS = os.getenv(
    'CORS_ALLOWED_ORIGINS', 'http://localhost:3000'
).split(',')

CSRF_TRUSTED_ORIGINS = [
    'http://mastersat.uz',
    'https://mastersat.uz',
    'http://www.mastersat.uz',
    'https://www.mastersat.uz',
    'https://admin.mastersat.uz',
    'https://questions.mastersat.uz',
    'https://teacher.mastersat.uz',
    'http://65.109.100.104',
]

# Allow extra trusted origins from env (e.g. http://localhost:3000 in dev)
_extra_csrf = os.getenv('CSRF_TRUSTED_ORIGINS_EXTRA', '')
if _extra_csrf:
    CSRF_TRUSTED_ORIGINS += [o.strip() for o in _extra_csrf.split(',') if o.strip()]

# Always trust localhost in DEBUG mode so `npm run dev` works without extra config
if DEBUG:
    CSRF_TRUSTED_ORIGINS += ['http://localhost:3000', 'http://127.0.0.1:3000',
                              'http://localhost:8000', 'http://127.0.0.1:8000']

# Cookie-based JWT auth still requires CSRF defenses for unsafe requests.
# Lax is more resilient across subdomain navigations while still preventing most CSRF vectors.
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False

# Share CSRF + session cookies across subdomains in production so the admin/questions/teacher
# consoles can complete login/refresh flows after navigating from the apex domain.
if not DEBUG:
    SESSION_COOKIE_DOMAIN = ".mastersat.uz"
    CSRF_COOKIE_DOMAIN = ".mastersat.uz"


# ─── Classroom homework (submissions) ─────────────────────────────────────────
# Max size per file; comma-separated lower-case extensions including the dot (e.g. ".pdf,.png").
CLASSROOM_SUBMISSION_MAX_FILE_BYTES = int(
    os.getenv("CLASSROOM_SUBMISSION_MAX_FILE_BYTES", str(15 * 1024 * 1024))
)
CLASSROOM_SUBMISSION_ALLOWED_FILE_EXTENSIONS = frozenset(
    x.strip().lower()
    for x in os.getenv(
        "CLASSROOM_SUBMISSION_ALLOWED_FILE_EXTENSIONS",
        ".pdf,.png,.jpg,.jpeg,.gif,.webp,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt",
    ).split(",")
    if x.strip()
)
CLASSROOM_SUBMISSION_GRADE_MIN = int(os.getenv("CLASSROOM_SUBMISSION_GRADE_MIN", "0"))
CLASSROOM_SUBMISSION_GRADE_MAX = int(os.getenv("CLASSROOM_SUBMISSION_GRADE_MAX", "100"))

# Homework grade leaderboard: minimum reviewed submissions before assigning a confident rank (null rank below).
CLASSROOM_LEADERBOARD_MIN_REVIEWED_FOR_RANK = int(os.getenv("CLASSROOM_LEADERBOARD_MIN_REVIEWED_FOR_RANK", "2"))

# Homework submission: caps and per-user submit throttle (DRF scope ``homework_submit``).
CLASSROOM_SUBMISSION_MAX_FILES_PER_SUBMISSION = int(os.getenv("CLASSROOM_SUBMISSION_MAX_FILES_PER_SUBMISSION", "50"))
CLASSROOM_SUBMISSION_MAX_BATCH_BYTES = int(
    os.getenv("CLASSROOM_SUBMISSION_MAX_BATCH_BYTES", str(100 * 1024 * 1024))
)

# Prune ``HomeworkStagedUpload`` rows (status=attached) older than this many days.
CLASSROOM_HOMEWORK_STAGED_RETENTION_DAYS = int(os.getenv("CLASSROOM_HOMEWORK_STAGED_RETENTION_DAYS", "30"))

# Ops alerting: Slack/webhook + optional email for CRITICAL homework/storage events.
# Dedupe / cooldown uses default cache (Redis in prod); see CLASSROOM_ALERT_COOLDOWN_SECONDS.
CLASSROOM_OPS_WEBHOOK_URL = os.getenv("CLASSROOM_OPS_WEBHOOK_URL", "").strip()
CLASSROOM_OPS_EMAIL_RECIPIENTS = os.getenv("CLASSROOM_OPS_EMAIL_RECIPIENTS", "").strip()


# JWT: optionally hard-reject authenticated API tokens when ``security_step_up_required_until``
# is active. Default False: rely on refresh/login/session flows instead of denying every JWT.
SECURITY_STEP_UP_ENFORCE_ON_JWT = _env_bool(
    "SECURITY_STEP_UP_ENFORCE_ON_JWT", default_when_unset=False
)

# ─── Django REST Framework ────────────────────────────────────────────────────

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        # Cookie + header (defense-in-depth and backward compatibility for non-browser clients).
        'users.authentication.CookieOrHeaderJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'users.permissions.IsAuthenticatedAndNotFrozen',
    ),
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': {
        'anon': None,
        'user': None,
        'burst': None,
        'sustained': None,
        'homework_submit': os.getenv('CLASSROOM_HOMEWORK_SUBMIT_THROTTLE', '120/hour'),
        'homework_submit_global': os.getenv('CLASSROOM_HOMEWORK_SUBMIT_GLOBAL_THROTTLE', '5000/hour'),
        'homework_submit_class': os.getenv('CLASSROOM_HOMEWORK_SUBMIT_PER_CLASS_THROTTLE', '800/hour'),
        # Assessments: per-attempt answer writes.
        'assessment_answer': os.getenv('ASSESSMENT_ANSWER_THROTTLE', '60/minute'),
        # Assessments: staff homework assignment actions.
        'assessment_assign': os.getenv('ASSESSMENT_ASSIGN_THROTTLE', '30/minute'),
        # Per classroom (all staff combined) and global (entire system).
        'assessment_assign_classroom': os.getenv('ASSESSMENT_ASSIGN_CLASSROOM_THROTTLE', '120/hour'),
        'assessment_assign_global': os.getenv('ASSESSMENT_ASSIGN_GLOBAL_THROTTLE', '2000/hour'),
        # SPA auth client telemetry (batched; default allows ~1 flush/min + beacons + retries).
        'client_auth_telemetry': os.getenv('AUTH_CLIENT_TELEMETRY_THROTTLE', '120/hour'),
        # Tighter limit when a classroom is under mitigation (auto after abuse spike).
        'assessment_assign_classroom_mitigated': os.getenv(
            'ASSESSMENT_ASSIGN_CLASSROOM_MITIGATED_THROTTLE',
            '40/hour',
        ),
    }
    ,
    # Standardize core AppError responses.
    "EXCEPTION_HANDLER": "core.errors.drf.core_exception_handler",
    # OpenAPI schema generator (used for frontend type generation).
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "MasterSAT LMS API",
    "VERSION": "1.0.0",
    # Cookie auth: documented as such (clients are same-origin on subdomains).
    "SERVE_AUTHENTICATION": [],
    "SERVE_PERMISSIONS": [],
}


# ─── Django Admin Theme ───────────────────────────────────────────────────────

JAZZMIN_SETTINGS = {
    "site_title": "MasterSAT Admin",
    "site_header": "MasterSAT Portal",
    "site_brand": "MasterSAT",
    "welcome_sign": "Welcome to the MasterSAT Admin",
    "copyright": "MasterSAT Center",
    "user_avatar": None,
    "show_ui_builder": False,
    "changeform_format": "single",
    "related_modal_active": True,
}


# ─── Security Hardening (Production only) ─────────────────────────────────────

if not DEBUG:
    # Behind Nginx/SSL termination
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

    # HSTS is powerful and can be hard to roll back.
    # Enable explicitly only after confirming HTTPS is correct for all subdomains.
    ENABLE_HSTS = os.getenv("ENABLE_HSTS", "False").lower() == "true"
    if ENABLE_HSTS:
        SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
        SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "False").lower() == "true"
        SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "False").lower() == "true"

# Telegram OIDC login opens a popup at oauth.telegram.org and posts back via window.opener.
# Django defaults to "same-origin" which blocks cross-origin opener access — break the popup callback.
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"


# ─── Logging ──────────────────────────────────────────────────────────────────

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING' if not DEBUG else 'DEBUG',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING' if not DEBUG else 'INFO',
            'propagate': False,
        },
    },
}


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
