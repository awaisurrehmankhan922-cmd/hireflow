import hashlib
import hmac
import json
import os
import time

os.environ.update(DATABASE_URL=os.environ.get("TEST_DATABASE_URL", "sqlite:////tmp/hireflow_test.db"), LLM_PROVIDER="mock", WEBHOOK_SECRET="test-secret",
                  ADMIN_EMAIL="admin@test.com", ADMIN_PASSWORD="supersecret123", JWT_SECRET="jwt-test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.llm.factory import set_provider  # noqa: E402
from app.llm.providers import MockProvider  # noqa: E402
from app.main import app, bootstrap  # noqa: E402
from app.services.mailer import MemoryTransport, set_transport  # noqa: E402


@pytest.fixture()
def outbox():
    t = MemoryTransport()
    set_transport(t)
    return t


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    bootstrap()
    MockProvider.available = True
    set_provider(MockProvider())
    yield
    set_provider(None)


@pytest.fixture()
def client(outbox):
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"email": "admin@test.com", "password": "supersecret123"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c


def sign(body: bytes, secret="test-secret", ts=None):
    ts = ts or int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return {"X-HireFlow-Timestamp": str(ts), "X-HireFlow-Signature": sig, "Content-Type": "application/json"}


@pytest.fixture()
def submit(client):
    def _submit(entry_id="101", email="maria@example.com", position="Housekeeping Supervisor", **extra):
        payload = {"entry_id": entry_id, "form_id": "3", "email": email, "full_name": "Maria Santos",
                   "phone": "+971500000000", "position": position,
                   "fields": {"experience": "6 years hotel housekeeping", "nationality": "PH"}} | extra
        body = json.dumps(payload).encode()
        return client.post("/api/webhooks/wordpress", content=body, headers=sign(body))
    return _submit
