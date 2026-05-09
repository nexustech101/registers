"""
Password helpers for registry-managed models.

The registers intentionally uses only the Python standard library here so
password hashing stays available without pulling in another runtime
dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
from typing import Any

from registers.db.exceptions import ConfigurationError

# @TODO: Consider adding support for other hashing schemes in the future + more tools for JWT auth

PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 600_000
_PASSWORD_PARTS = 4


@dataclass(frozen=True)
class PasswordHashPolicy:
    """Configurable password hashing policy."""

    scheme: str = PASSWORD_HASH_SCHEME
    iterations: int = PASSWORD_HASH_ITERATIONS
    argon2_time_cost: int = 2
    argon2_memory_cost: int = 19 * 1024
    argon2_parallelism: int = 1

    def __post_init__(self) -> None:
        if self.scheme not in {"pbkdf2_sha256", "argon2id"}:
            raise ConfigurationError("PasswordHashPolicy.scheme must be 'pbkdf2_sha256' or 'argon2id'.")
        if self.iterations <= 0:
            raise ConfigurationError("PasswordHashPolicy.iterations must be positive.")
        if self.argon2_time_cost <= 0 or self.argon2_memory_cost <= 0 or self.argon2_parallelism <= 0:
            raise ConfigurationError("Argon2id policy parameters must be positive.")


_CURRENT_POLICY = PasswordHashPolicy()


def configure_password_policy(policy: PasswordHashPolicy) -> PasswordHashPolicy:
    """Set the process-local password hashing policy and return the previous policy."""
    global _CURRENT_POLICY
    previous = _CURRENT_POLICY
    _CURRENT_POLICY = policy
    return previous


def get_password_policy() -> PasswordHashPolicy:
    """Return the active process-local password hashing policy."""
    return _CURRENT_POLICY


def hash_password(
    password: str,
    *,
    iterations: int | None = None,
    policy: PasswordHashPolicy | None = None,
) -> str:
    """Return a salted password hash using the active policy."""
    resolved = policy or _CURRENT_POLICY
    if iterations is not None:
        resolved = PasswordHashPolicy(
            scheme="pbkdf2_sha256",
            iterations=iterations,
            argon2_time_cost=resolved.argon2_time_cost,
            argon2_memory_cost=resolved.argon2_memory_cost,
            argon2_parallelism=resolved.argon2_parallelism,
        )
    if resolved.scheme == "argon2id":
        return _hash_argon2id(password, resolved)
    return _hash_pbkdf2(password, resolved.iterations)


def _hash_pbkdf2(password: str, iterations: int) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        iterations,
    ).hex()
    return f"{PASSWORD_HASH_SCHEME}${iterations}${salt}${digest}"


def _hash_argon2id(password: str, policy: PasswordHashPolicy) -> str:
    try:
        from argon2.low_level import Type, hash_secret
    except ImportError as exc:  # pragma: no cover - optional dependency path
        raise ConfigurationError(
            "Argon2id password hashing requires the optional 'argon2-cffi' package."
        ) from exc

    salt = secrets.token_bytes(16)
    return hash_secret(
        password.encode("utf-8"),
        salt,
        time_cost=policy.argon2_time_cost,
        memory_cost=policy.argon2_memory_cost,
        parallelism=policy.argon2_parallelism,
        hash_len=32,
        type=Type.ID,
    ).decode("ascii")


def is_password_hash(value: Any) -> bool:
    """Return True when *value* matches this module's hash format."""
    if not isinstance(value, str):
        return False
    if value.startswith("$argon2id$"):
        return True

    parts = value.split("$")
    if len(parts) != _PASSWORD_PARTS:
        return False
    scheme, iterations, salt, digest = parts
    if scheme != PASSWORD_HASH_SCHEME:
        return False
    if not iterations.isdigit():
        return False
    return bool(salt) and bool(digest)


def verify_password(password: str, stored_hash: str) -> bool:
    """Return True when *password* matches *stored_hash*."""
    if not is_password_hash(stored_hash):
        return False
    if stored_hash.startswith("$argon2id$"):
        return _verify_argon2id(password, stored_hash)

    _, iterations, salt, digest = stored_hash.split("$", maxsplit=3)
    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        int(iterations),
    ).hex()
    return hmac.compare_digest(candidate, digest)


def _verify_argon2id(password: str, stored_hash: str) -> bool:
    try:
        from argon2.exceptions import VerifyMismatchError
        from argon2.low_level import Type, verify_secret
    except ImportError as exc:  # pragma: no cover - optional dependency path
        raise ConfigurationError(
            "Argon2id password verification requires the optional 'argon2-cffi' package."
        ) from exc

    try:
        return verify_secret(stored_hash.encode("ascii"), password.encode("utf-8"), Type.ID)
    except VerifyMismatchError:
        return False


def verify_and_upgrade_password(
    password: str,
    stored_hash: str,
    *,
    policy: PasswordHashPolicy | None = None,
) -> tuple[bool, str | None]:
    """
    Verify a password and return an upgraded hash when the stored hash is stale.

    The returned tuple is ``(verified, upgraded_hash)``. ``upgraded_hash`` is
    ``None`` when verification fails or the stored hash already satisfies policy.
    """
    if not verify_password(password, stored_hash):
        return False, None
    resolved = policy or _CURRENT_POLICY
    if not _needs_upgrade(stored_hash, resolved):
        return True, None
    return True, hash_password(password, policy=resolved)


def _needs_upgrade(stored_hash: str, policy: PasswordHashPolicy) -> bool:
    if policy.scheme == "argon2id":
        return not stored_hash.startswith("$argon2id$")
    if stored_hash.startswith("$argon2id$"):
        return policy.scheme != "argon2id"

    parts = stored_hash.split("$")
    if len(parts) != _PASSWORD_PARTS:
        return True
    scheme, iterations, _salt, _digest = parts
    if scheme != policy.scheme:
        return True
    if not iterations.isdigit():
        return True
    return int(iterations) < policy.iterations
