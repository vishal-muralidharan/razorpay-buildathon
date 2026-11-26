import os
import sys
from pathlib import Path
import pytest

# Ensure backend root is on sys.path
backend_root = str(Path(__file__).resolve().parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

# Ensure environment variable is set before any module imports auth
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-with-at-least-32-bytes-length")


@pytest.fixture(scope="session", autouse=True)
def jwt_secret_fixture():
    test_secret = "test-jwt-secret-with-at-least-32-bytes-length"
    os.environ["JWT_SECRET"] = test_secret
    import app.auth as auth_module
    auth_module.JWT_SECRET = test_secret
    yield test_secret
