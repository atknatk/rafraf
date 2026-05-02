"""Top-level pytest fixtures for the RafRaf backend test suite.

Provides a session-scoped RSA keypair so JWT RS256 (T2.9) works during
tests without requiring an out-of-band ``infra/scripts/generate-jwt-keys.sh``
invocation. The keypair is written to a tmp dir and the cached settings
singleton is patched to point at it.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import app.core.config as config_module
import app.core.security as security_module


def _generate_rsa_keypair(target_dir: Path) -> tuple[Path, Path]:
    """Generate a 2048-bit RSA keypair and write PEM files. Returns (priv, pub)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    priv_path = target_dir / "jwt_private.pem"
    pub_path = target_dir / "jwt_public.pem"

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    pub_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return priv_path, pub_path


@pytest.fixture(scope="session", autouse=True)
def _jwt_rs256_test_keys(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Generate an RSA keypair for the test session and wire it into Settings.

    Without this autouse fixture, every test that calls
    ``create_access_token`` would fail because RS256 (the new default)
    has no key on disk. Also configures the legacy HS256 grace period so
    the migration tests can verify both paths.
    """
    keys_dir = tmp_path_factory.mktemp("jwt_keys")
    priv, pub = _generate_rsa_keypair(keys_dir)

    settings = config_module.get_settings()
    # Patch the cached singleton so all code paths see the test keypair.
    settings.jwt_private_key_path = str(priv)
    settings.jwt_public_key_path = str(pub)
    settings.jwt_algorithm = "RS256"
    # Default to grace period ACTIVE so HS256 fallback works in tests that
    # don't explicitly override it.
    settings.jwt_legacy_hs256_secret = settings.jwt_secret_key
    settings.jwt_legacy_grace_until = datetime.now(tz=UTC) + timedelta(days=365)

    security_module.reset_key_cache()
    try:
        yield
    finally:
        security_module.reset_key_cache()
