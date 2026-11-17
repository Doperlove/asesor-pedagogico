import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="asesor_test_"))
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_TMP / 'test.db'}",
    "STORAGE_DIR": str(_TMP / "storage"),
    "SEED_DEMO": "false",
    "SECRET_KEY": "clave-de-pruebas-suficientemente-larga-para-hs256-0123456789",
    "LLM_PROVIDER": "mock",
    "DEMO_PASSWORD": "Clave-Pruebas-2026",
    "SANDBOX_TIMEOUT_S": "20",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASSWORD = "Clave-Pruebas-2026"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.db import SessionLocal, init_db
    from app.main import app
    from app.seed import seed

    init_db()
    with SessionLocal() as db:
        seed(db, con_historial=False)
    with TestClient(app) as c:
        yield c


def login(client, email: str) -> dict:
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["usuario"]


@pytest.fixture
def rubrica_valida():
    from app.demo_content import rubrica_harness

    return rubrica_harness("Lab prueba", "pruebas")
