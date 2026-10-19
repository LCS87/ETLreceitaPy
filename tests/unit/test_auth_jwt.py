"""
Testes de autenticação JWT da API (login, /me e proteção de endpoints).

Não exige PostgreSQL: endpoints protegidos que acessam banco são validados
pela ausência de 401/403 (auth passou; erro de DB é esperado sem banco).
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

API_TEST_KEY = "test-api-key-123"
PASSWORD = "senha-segura-123"


@pytest.fixture
def auth_env(tmp_path, monkeypatch):
    """Usuário de teste em arquivo temporário + API_KEY ativada no app."""
    from src.api.auth import create_or_update_user

    users_file = tmp_path / "users.json"
    monkeypatch.setenv("USERS_FILE", str(users_file))
    create_or_update_user("leo", PASSWORD, role="admin", tenant_id="tenant-1")

    # API_KEY é lida na importação do main; patch direto no atributo do módulo
    monkeypatch.setattr("src.api.main.API_KEY", API_TEST_KEY)

    from src.api.main import app
    return TestClient(app)


def _login(client: TestClient, username: str = "leo", password: str = PASSWORD) -> str:
    r = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestLogin:
    """Endpoint POST /api/v1/auth/login."""

    def test_login_success(self, auth_env):
        r = auth_env.post("/api/v1/auth/login", json={"username": "leo", "password": PASSWORD})
        assert r.status_code == 200
        body = r.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["expires_in"] > 0

    def test_login_wrong_password(self, auth_env):
        r = auth_env.post("/api/v1/auth/login", json={"username": "leo", "password": "errada"})
        assert r.status_code == 401

    def test_login_unknown_user(self, auth_env):
        r = auth_env.post("/api/v1/auth/login", json={"username": "nao-existe", "password": PASSWORD})
        assert r.status_code == 401

    def test_login_does_not_leak_hash(self, auth_env):
        r = auth_env.post("/api/v1/auth/login", json={"username": "leo", "password": PASSWORD})
        assert "password_hash" not in r.text


class TestMe:
    """Endpoint GET /api/v1/auth/me (validação do Bearer JWT)."""

    def test_me_with_valid_token(self, auth_env):
        token = _login(auth_env)
        r = auth_env.get("/api/v1/auth/me", headers=_bearer(token))
        assert r.status_code == 200
        assert r.json() == {"username": "leo", "role": "admin", "tenant_id": "tenant-1"}

    def test_me_without_token(self, auth_env):
        assert auth_env.get("/api/v1/auth/me").status_code == 401

    def test_me_with_garbage_token(self, auth_env):
        assert auth_env.get("/api/v1/auth/me", headers=_bearer("token-invalido")).status_code == 401

    def test_me_with_expired_token(self, auth_env):
        from src.api.auth import create_access_token

        expired = create_access_token({"sub": "leo"}, expires_delta=timedelta(seconds=-1))
        assert auth_env.get("/api/v1/auth/me", headers=_bearer(expired)).status_code == 401

    def test_me_after_user_removed(self, auth_env, tmp_path, monkeypatch):
        """Revogação: token deixa de valer quando o usuário sai do arquivo."""
        token = _login(auth_env)
        empty = tmp_path / "empty.json"
        empty.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("USERS_FILE", str(empty))
        assert auth_env.get("/api/v1/auth/me", headers=_bearer(token)).status_code == 401


class TestProtectedEndpoints:
    """Dependência combinada: API Key OU JWT nos endpoints de dados."""

    def test_no_credentials_returns_403(self, auth_env):
        assert auth_env.get("/api/v1/leads?uf=PE").status_code == 403

    def test_with_valid_api_key(self, auth_env):
        r = auth_env.get("/api/v1/leads?uf=PE", headers={"X-API-Key": API_TEST_KEY})
        assert r.status_code not in (401, 403), "API Key válida deve autenticar"

    def test_with_invalid_api_key(self, auth_env):
        assert auth_env.get("/api/v1/leads?uf=PE", headers={"X-API-Key": "errada"}).status_code == 403

    def test_with_valid_jwt(self, auth_env):
        token = _login(auth_env)
        r = auth_env.get("/api/v1/leads?uf=PE", headers=_bearer(token))
        assert r.status_code not in (401, 403), "JWT válido deve autenticar"

    def test_with_invalid_jwt(self, auth_env):
        r = auth_env.get("/api/v1/leads?uf=PE", headers=_bearer("abc.def.ghi"))
        assert r.status_code == 401

    def test_with_expired_jwt(self, auth_env):
        from src.api.auth import create_access_token

        expired = create_access_token({"sub": "leo"}, expires_delta=timedelta(seconds=-1))
        assert auth_env.get("/api/v1/leads?uf=PE", headers=_bearer(expired)).status_code == 401

    def test_dev_mode_without_api_key(self, auth_env, monkeypatch):
        """Sem API_KEY no ambiente, auth fica desabilitada (modo dev)."""
        monkeypatch.setattr("src.api.main.API_KEY", "")
        r = auth_env.get("/api/v1/leads?uf=PE")
        assert r.status_code not in (401, 403)


class TestUserStore:
    """Store de usuários: hash bcrypt e autenticação."""

    def test_roundtrip_create_and_authenticate(self, auth_env):
        from src.api.auth import authenticate_user

        user = authenticate_user("leo", PASSWORD)
        assert user is not None
        assert user["role"] == "admin"
        assert "password_hash" not in user

    def test_authenticate_wrong_password(self, auth_env):
        from src.api.auth import authenticate_user

        assert authenticate_user("leo", "errada") is None

    def test_authenticate_unknown_user(self, auth_env):
        from src.api.auth import authenticate_user

        assert authenticate_user("desconhecido", PASSWORD) is None

    def test_hash_is_bcrypt_and_verifiable(self):
        from src.api.auth import get_password_hash, verify_password

        h = get_password_hash(PASSWORD)
        assert h.startswith("$2b$")
        assert verify_password(PASSWORD, h)
        assert not verify_password("outra", h)

    def test_long_password_truncated_safely(self):
        from src.api.auth import get_password_hash, verify_password

        long_pwd = "x" * 200  # bcrypt limita a 72 bytes
        h = get_password_hash(long_pwd)
        assert verify_password(long_pwd, h)
        assert verify_password(long_pwd[:72], h)
