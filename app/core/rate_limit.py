import logging
import math
from typing import Literal
from uuid import UUID

from redis.exceptions import RedisError

from app.core.config import settings
from app.core.queue import get_redis_connection
from app.core.request_errors import RequestNotStartedError

logger = logging.getLogger(__name__)
Bucket = Literal["ask", "semantic_search", "organize", "export", "ai_processing"]
AuthRateLimitAction = Literal["sign_up", "sign_in", "verification", "password_reset"]

# Atomic across API instances and workers; denials do not extend the window.
ADMIT_SCRIPT = """
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
local ttl = redis.call('PTTL', KEYS[1])
if ttl < 0 then
    redis.call('DEL', KEYS[1])
    count = 0
end
if count >= tonumber(ARGV[1]) then
    return {0, math.max(ttl, 1)}
end
redis.call('INCR', KEYS[1])
if count == 0 then
    redis.call('PEXPIRE', KEYS[1], ARGV[2])
    ttl = tonumber(ARGV[2])
end
return {1, ttl}
"""


def _enforce_keyed_rate_limit(key: str, limit: int, seconds: int, label: str) -> None:
    try:
        allowed, ttl_ms = get_redis_connection().eval(
            ADMIT_SCRIPT, 1, key, limit, seconds * 1000,
        )
    except RedisError as error:
        logger.warning(
            "Request admission unavailable: label=%s error_type=%s", label, type(error).__name__,
        )
        raise RequestNotStartedError(
            503, "Request limits are temporarily unavailable. Try again in 30 seconds.",
            headers={"Retry-After": "30"},
        ) from error
    if not allowed:
        retry_after = max(1, math.ceil(int(ttl_ms) / 1000))
        raise RequestNotStartedError(
            429, f"{label} limit reached. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


def enforce_rate_limit(user_id: UUID, bucket: Bucket) -> None:
    if not settings.rate_limits_enabled:
        return
    policies = {
        "ask": (settings.rate_limit_ask_per_minute, 60, "Questions"),
        "semantic_search": (settings.rate_limit_search_per_minute, 60, "AI searches"),
        "organize": (settings.rate_limit_organize_per_minute, 60, "Organization retries"),
        "export": (settings.rate_limit_exports_per_hour, 3600, "Exports"),
        "ai_processing": (settings.rate_limit_ai_jobs_per_minute, 60, "AI processing"),
    }
    limit, seconds, label = policies[bucket]
    _enforce_keyed_rate_limit(f"mind-palace:rate:{bucket}:{user_id}", limit, seconds, label)


def enforce_auth_rate_limit(client_key: str, action: AuthRateLimitAction) -> None:
    if not settings.auth_rate_limits_enabled:
        return
    policies = {
        "sign_up": (settings.auth_rate_limit_sign_up_per_window, 600, "Sign-up"),
        "sign_in": (settings.auth_rate_limit_sign_in_per_window, 300, "Sign-in"),
        "verification": (settings.auth_rate_limit_verification_per_window, 600, "Verification"),
        "password_reset": (
            settings.auth_rate_limit_password_reset_per_window,
            900,
            "Password reset",
        ),
    }
    limit, seconds, label = policies[action]
    _enforce_keyed_rate_limit(
        f"mind-palace:rate:auth:{action}:{client_key}", limit, seconds, label,
    )
