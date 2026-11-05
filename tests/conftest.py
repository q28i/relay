"""
Pytest configuration ensuring project root is in sys.path and isolating the test database.
"""

import sys
import os
import tempfile
import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Create an isolated temporary test database directory for the test session
_test_db_dir = tempfile.mkdtemp(prefix="relay_test_")
_test_db_path = os.path.join(_test_db_dir, "test_whatsapp_web.db")
os.environ["RELAY_DB_PATH"] = _test_db_path

from backend.database import db
db.set_db_path(_test_db_path)


@pytest.fixture(scope="session", autouse=True)
def isolate_test_database():
    """Ensures tests run in a completely isolated database and clean up afterward."""
    yield _test_db_path
    # Cleanup after session
    try:
        if os.path.exists(_test_db_path):
            os.remove(_test_db_path)
        if os.path.exists(_test_db_dir):
            os.rmdir(_test_db_dir)
    except Exception:
        pass


@pytest.fixture(scope="session")
def session_db(isolate_test_database):
    """Provides path to isolated session test database."""
    return isolate_test_database


