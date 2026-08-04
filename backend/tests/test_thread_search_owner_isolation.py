"""Contrato de isolamento de threads.search (fix-thread-list-user-isolation).

Cobre as units da task-auth-1:
- unit-1: search HTTP isola por owner (dois usuários)
- unit-2: thread sem owner ausente do search de role=user
- unit-3: role=user não recebe bypass (FilterType efetivo)

Os testes HTTP batem no backend real (`JEFF_AI_API_URL`, default
http://localhost:8001) quando alcançável; caso contrário são skipped —
o wiring estático em `test_langgraph_auth.py` (LANGGRAPH_AUTH no compose)
garante a regressão no CI sem depender do container.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any, Sequence

import httpx
import pytest
from langgraph_sdk.auth import types as auth_types

from src.infrastructure.auth.security import get_password_hash
from src.infrastructure.web.auth import authorize_by_owner

_API_URL = os.environ.get("JEFF_AI_API_URL", "http://localhost:8001").rstrip("/")


@dataclass
class _FakeUser:
    identity: str
    permissions: Sequence[str] = ("user",)
    is_authenticated: bool = True
    display_name: str = "test"


def _auth_ctx(
    identity: str,
    *,
    resource: str,
    action: str,
    permissions: Sequence[str] = ("user",),
) -> auth_types.AuthContext:
    user = _FakeUser(identity=identity, permissions=permissions)
    return auth_types.AuthContext(
        user=user,  # type: ignore[arg-type]
        permissions=list(permissions),
        resource=resource,  # type: ignore[arg-type]
        action=action,  # type: ignore[arg-type]
    )


# --- unit-3: FilterType para role=user (não bypass) --------------------------


@pytest.mark.asyncio
async def test_user_role_search_returns_owner_filter_not_empty() -> None:
    """unit-3 / REQ-004: role=user recebe {\"owner\": identity}, não {}."""
    ctx = _auth_ctx("user-u", resource="threads", action="search")
    result = await authorize_by_owner(ctx, {})
    assert result == {"owner": "user-u"}


@pytest.mark.asyncio
async def test_admin_role_search_bypasses_owner_filter() -> None:
    ctx = _auth_ctx(
        "admin-1", resource="threads", action="search", permissions=("admin",)
    )
    result = await authorize_by_owner(ctx, {})
    assert result == {}


# --- HTTP helpers ------------------------------------------------------------


def _backend_reachable() -> bool:
    try:
        r = httpx.get(f"{_API_URL}/ok", timeout=2.0)
        return r.status_code < 500
    except Exception:
        return False


pytestmark_http = pytest.mark.skipif(
    not _backend_reachable(),
    reason=f"backend em {_API_URL} inacessível (subir docker / set JEFF_AI_API_URL)",
)


def _login(client: httpx.Client, username: str, password: str) -> None:
    """Login e força o cookie `session` no client.

    O cookie é emitido com `Secure` (auth_router). httpx não reenvia cookies
    Secure em `http://` — o browser em localhost costuma aceitar; nos testes
    HTTP lemos o Set-Cookie e setamos o header manualmente.
    """
    res = client.post(
        f"{_API_URL}/public/login",
        json={"username": username, "password": password},
    )
    assert res.status_code == 200, res.text
    token = res.cookies.get("session")
    if not token:
        # Fallback: parse Set-Cookie quando httpx não materializa cookie Secure.
        raw = res.headers.get("set-cookie") or ""
        if "session=" in raw:
            token = raw.split("session=", 1)[1].split(";", 1)[0]
    assert token, f"login sem cookie session: {res.headers.get('set-cookie')}"
    # Sem domain=…: com domain="localhost" o httpx às vezes não reenvia em :port.
    # Header explícito evita o filtro de cookies Secure em http://.
    client.cookies.clear()
    client.headers["Cookie"] = f"session={token}"


def _create_user_via_sql(username: str, password: str, role: str = "user") -> str:
    """Cria usuário descartável no Postgres do compose (psql via docker)."""
    import subprocess

    user_id = str(uuid.uuid4())
    pw_hash = get_password_hash(password)
    sql = (
        "INSERT INTO users (id, username, password_hash, role, is_active) "
        f"VALUES ('{user_id}', '{username}', '{pw_hash}', '{role}', true) "
        "ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash "
        f"RETURNING id;"
    )
    # Prefer docker exec; fall back to skip if unavailable.
    try:
        out = subprocess.check_output(
            [
                "docker",
                "exec",
                "jeff_ia_postgres",
                "psql",
                "-U",
                "jeff_ia",
                "-d",
                "jeff_ia",
                "-tAc",
                sql,
            ],
            text=True,
            stderr=subprocess.STDOUT,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        pytest.skip(f"não foi possível criar usuário de teste no Postgres: {exc}")
    # psql às vezes anexa "INSERT 0 1" mesmo com -tA; fica com a 1ª linha UUID.
    for line in out.splitlines():
        candidate = line.strip()
        if candidate and " " not in candidate and len(candidate) >= 32:
            return candidate
    return user_id


def _delete_user_via_sql(user_id: str) -> None:
    import subprocess

    try:
        subprocess.check_call(
            [
                "docker",
                "exec",
                "jeff_ia_postgres",
                "psql",
                "-U",
                "jeff_ia",
                "-d",
                "jeff_ia",
                "-c",
                f"DELETE FROM sessions WHERE user_id = '{user_id}'; "
                f"DELETE FROM users WHERE id = '{user_id}';",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass


def _create_thread(client: httpx.Client, *, owner_hint: str | None = None) -> dict[str, Any]:
    metadata: dict[str, Any] = {"graph_id": "unified"}
    if owner_hint is not None:
        # Cliente NÃO deve poder forçar owner — o server deve sobrescrever.
        metadata["owner"] = owner_hint
    res = client.post(f"{_API_URL}/threads", json={"metadata": metadata})
    assert res.status_code == 200, res.text
    return res.json()


def _search_threads(client: httpx.Client) -> list[dict[str, Any]]:
    res = client.post(
        f"{_API_URL}/threads/search",
        json={"limit": 100, "offset": 0},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body, list)
    return body


# --- unit-1 / unit-2: contrato HTTP -----------------------------------------


@pytestmark_http
def test_http_search_isolates_threads_by_owner() -> None:
    """unit-1 / REQ-ADD-001: user U não vê threads de V."""
    suffix = uuid.uuid4().hex[:8]
    user_u = f"iso-u-{suffix}"
    user_v = f"iso-v-{suffix}"
    password = "iso-test-pass"
    id_u = _create_user_via_sql(user_u, password)
    id_v = _create_user_via_sql(user_v, password)
    thread_v_id: str | None = None
    try:
        with httpx.Client(timeout=10.0) as client_v:
            _login(client_v, user_v, password)
            thread_v = _create_thread(client_v)
            thread_v_id = thread_v["thread_id"]
            assert (thread_v.get("metadata") or {}).get("owner") == id_v, (
                "create deve carimbar metadata.owner com users.id da sessão "
                f"(got {thread_v.get('metadata')})"
            )

        with httpx.Client(timeout=10.0) as client_u:
            _login(client_u, user_u, password)
            own = _create_thread(client_u)
            assert (own.get("metadata") or {}).get("owner") == id_u
            results = _search_threads(client_u)
            ids = {t["thread_id"] for t in results}
            owners = {(t.get("metadata") or {}).get("owner") for t in results}
            assert thread_v_id not in ids
            assert None not in owners  # unit-2: sem owner não aparece
            assert owners <= {id_u}
            assert own["thread_id"] in ids
    finally:
        if thread_v_id:
            # best-effort cleanup of V's thread as V
            try:
                with httpx.Client(timeout=10.0) as client_v:
                    _login(client_v, user_v, password)
                    client_v.delete(f"{_API_URL}/threads/{thread_v_id}")
            except Exception:
                pass
        _delete_user_via_sql(id_u)
        _delete_user_via_sql(id_v)


@pytestmark_http
def test_http_search_omits_threads_without_owner() -> None:
    """unit-2 / REQ-ADD-002: legadas sem owner invisíveis a role=user."""
    suffix = uuid.uuid4().hex[:8]
    username = f"iso-legacy-{suffix}"
    password = "iso-test-pass"
    user_id = _create_user_via_sql(username, password)
    try:
        with httpx.Client(timeout=10.0) as client:
            _login(client, username, password)
            results = _search_threads(client)
            for t in results:
                assert (t.get("metadata") or {}).get("owner") is not None, (
                    f"thread sem owner vazou no search: {t.get('thread_id')}"
                )
                assert (t.get("metadata") or {}).get("owner") == user_id
    finally:
        _delete_user_via_sql(user_id)


# --- auth-2: get cross-user + create stamp -----------------------------------


@pytestmark_http
def test_http_get_foreign_thread_returns_404() -> None:
    """auth-2 unit-1 / REQ-002: GET de thread alheia → 404 sem vazamento."""
    suffix = uuid.uuid4().hex[:8]
    user_u = f"get-u-{suffix}"
    user_v = f"get-v-{suffix}"
    password = "iso-test-pass"
    id_u = _create_user_via_sql(user_u, password)
    id_v = _create_user_via_sql(user_v, password)
    thread_v_id: str | None = None
    try:
        with httpx.Client(timeout=10.0) as client_v:
            _login(client_v, user_v, password)
            thread_v = _create_thread(client_v)
            thread_v_id = thread_v["thread_id"]
            assert (thread_v.get("metadata") or {}).get("owner") == id_v

        with httpx.Client(timeout=10.0) as client_u:
            _login(client_u, user_u, password)
            res = client_u.get(f"{_API_URL}/threads/{thread_v_id}")
            assert res.status_code == 404, res.text
            payload = res.json()
            # 404 de autorização — sem estado/mensagens da thread alheia.
            assert "values" not in payload
            assert "messages" not in payload
            assert payload.get("metadata") is None or "owner" not in (
                payload.get("metadata") or {}
            )
    finally:
        if thread_v_id:
            try:
                with httpx.Client(timeout=10.0) as client_v:
                    _login(client_v, user_v, password)
                    client_v.delete(f"{_API_URL}/threads/{thread_v_id}")
            except Exception:
                pass
        _delete_user_via_sql(id_u)
        _delete_user_via_sql(id_v)


@pytestmark_http
def test_http_get_own_thread_returns_200() -> None:
    """auth-2 unit-2 / REQ-002: GET da própria thread → 200."""
    suffix = uuid.uuid4().hex[:8]
    username = f"get-own-{suffix}"
    password = "iso-test-pass"
    user_id = _create_user_via_sql(username, password)
    thread_id: str | None = None
    try:
        with httpx.Client(timeout=10.0) as client:
            _login(client, username, password)
            created = _create_thread(client)
            thread_id = created["thread_id"]
            res = client.get(f"{_API_URL}/threads/{thread_id}")
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["thread_id"] == thread_id
            assert (body.get("metadata") or {}).get("owner") == user_id
    finally:
        if thread_id:
            try:
                with httpx.Client(timeout=10.0) as client:
                    _login(client, username, password)
                    client.delete(f"{_API_URL}/threads/{thread_id}")
            except Exception:
                pass
        _delete_user_via_sql(user_id)


@pytestmark_http
def test_http_create_stamps_owner_ignoring_client_hint() -> None:
    """auth-2 unit-3 / REQ-003: create carimba owner da sessão, não do body."""
    suffix = uuid.uuid4().hex[:8]
    username = f"stamp-{suffix}"
    password = "iso-test-pass"
    user_id = _create_user_via_sql(username, password)
    thread_id: str | None = None
    try:
        with httpx.Client(timeout=10.0) as client:
            _login(client, username, password)
            forged = str(uuid.uuid4())
            created = _create_thread(client, owner_hint=forged)
            thread_id = created["thread_id"]
            assert (created.get("metadata") or {}).get("owner") == user_id
            assert (created.get("metadata") or {}).get("owner") != forged
    finally:
        if thread_id:
            try:
                with httpx.Client(timeout=10.0) as client:
                    _login(client, username, password)
                    client.delete(f"{_API_URL}/threads/{thread_id}")
            except Exception:
                pass
        _delete_user_via_sql(user_id)
