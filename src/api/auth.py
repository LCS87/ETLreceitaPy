"""
Autenticação da API — API Key e JWT (OAuth2 Password Flow).

- Usuários armazenados em arquivo JSON com hash bcrypt (`config/users.json`
  por padrão, configurável via variável `USERS_FILE`).
- Emissão e validação de tokens JWT (HS256) com `SECRET_KEY` do ambiente.
- CLI para criação de usuários: `python -m src.api.auth create <username>`.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import json
import os
from pathlib import Path

from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# Chave de assinatura JWT vinda do ambiente (obrigatória em produção)
SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "dev-only-secret-change-me-in-production",
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24)))

# Arquivo de usuários: variável USERS_FILE ou config/users.json na raiz do projeto
_DEFAULT_USERS_FILE = Path(__file__).resolve().parents[2] / "config" / "users.json"

# Scheme estrito (exige header Authorization: Bearer ...) — usado em /auth/me
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")
# Scheme opcional — usado na dependência combinada API Key OU JWT
optional_bearer = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)


def users_file_path() -> Path:
    """Caminho do arquivo de usuários (USERS_FILE ou padrão)."""
    return Path(os.getenv("USERS_FILE", str(_DEFAULT_USERS_FILE)))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica senha contra hash bcrypt (limite de 72 bytes do algoritmo)."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8")[:72],
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    """Gera hash bcrypt da senha (máx. 72 bytes, conforme limite do algoritmo)."""
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def load_users() -> Dict[str, Dict[str, Any]]:
    """Carrega o dicionário de usuários do arquivo JSON ({} se não existir)."""
    path = users_file_path()
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Autentica usuário; retorna o registro (sem o hash) ou None se inválido."""
    user = load_users().get(username)
    if not user or "password_hash" not in user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return {k: v for k, v in user.items() if k != "password_hash"}


def create_or_update_user(
    username: str,
    password: str,
    role: str = "user",
    tenant_id: str = "",
) -> None:
    """Cria ou atualiza um usuário no arquivo de usuários (hash bcrypt)."""
    path = users_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    users = load_users()
    users[username] = {
        "password_hash": get_password_hash(password),
        "role": role,
        "tenant_id": tenant_id,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Cria token JWT assinado com expiração."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_token_for_user(username: str, user: Dict[str, Any]) -> tuple[str, int]:
    """Gera token para um usuário; retorna (token, expiração em segundos)."""
    token = create_access_token({
        "sub": username,
        "role": user.get("role", "user"),
        "tenant_id": user.get("tenant_id", ""),
    })
    return token, ACCESS_TOKEN_EXPIRE_MINUTES * 60


async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """Dependency: valida o Bearer JWT e retorna o usuário do arquivo de usuários."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Usuário deve continuar existindo (revogação por remoção do arquivo)
    user = load_users().get(username)
    if user is None:
        raise credentials_exception
    return {
        "username": username,
        "role": user.get("role", "user"),
        "tenant_id": user.get("tenant_id", ""),
    }


def _main() -> None:
    """CLI: python -m src.api.auth create <username> [--role ROLE] [--tenant ID]"""
    import argparse
    import getpass

    parser = argparse.ArgumentParser(description="Gerencia usuários da API")
    sub = parser.add_subparsers(dest="command")
    create = sub.add_parser("create", help="Cria ou atualiza um usuário")
    create.add_argument("username")
    create.add_argument("--role", default="user", help="Papel do usuário (user/admin)")
    create.add_argument("--tenant", default="", help="tenant_id do usuário")
    args = parser.parse_args()

    if args.command == "create":
        password = getpass.getpass("Senha: ")
        confirm = getpass.getpass("Confirme a senha: ")
        if password != confirm:
            raise SystemExit("Senhas não conferem")
        create_or_update_user(args.username, password, args.role, args.tenant)
        print(f"Usuário '{args.username}' salvo em {users_file_path()}")
    else:
        parser.print_help()


if __name__ == "__main__":
    _main()
