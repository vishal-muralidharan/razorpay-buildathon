import inspect
import os
import pytest
from app import auth


def test_auth_module_has_no_literal_default():
    """Verify backend/app/auth.py contains no literal secret string or hardcoded default."""
    source = inspect.getsource(auth)
    assert "super-secret-demo-key-123" not in source
    assert 'os.getenv("JWT_SECRET",' not in source
    assert "os.getenv('JWT_SECRET'," not in source


def test_short_secret_gives_random(caplog):
    """Verify that an unset or short secret logs a warning and generates a random secret."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("JWT_SECRET", "short-secret")
        caplog.clear()
        with caplog.at_level("WARNING"):
            secret1 = auth._init_jwt_secret()
            assert len(secret1.encode("utf-8")) >= 32
            assert "JWT_SECRET is not set or is too short: using a random secret. Tokens stop working when the process restarts." in caplog.text

    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("JWT_SECRET", raising=False)
        caplog.clear()
        with caplog.at_level("WARNING"):
            secret2 = auth._init_jwt_secret()
            assert len(secret2.encode("utf-8")) >= 32
            assert secret1 != secret2
            assert "JWT_SECRET is not set or is too short: using a random secret. Tokens stop working when the process restarts." in caplog.text

    valid_secret = "a" * 32
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("JWT_SECRET", valid_secret)
        caplog.clear()
        with caplog.at_level("WARNING"):
            secret3 = auth._init_jwt_secret()
            assert secret3 == valid_secret
            assert "JWT_SECRET is not set" not in caplog.text


def test_oidc_issuer_warning_when_unset(caplog):
    """Verify that a warning is logged when OIDC_ISSUER is unset."""
    import importlib
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("OIDC_ISSUER", raising=False)
        caplog.clear()
        with caplog.at_level("WARNING"):
            importlib.reload(auth)
            assert "OIDC_ISSUER is not set: demo merchant tokens are accepted." in caplog.text
    # Reset auth module back with test JWT secret
    importlib.reload(auth)
