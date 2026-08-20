"""Testes de `mcp_config_store` (task `user-scoped-mcp-config-storage-task-store-3`).

Cobre REQ-001 do spec `user-mcp-server-store`: cada função de CRUD é
escopada por `user_id` e delega a um `McpServerRepositoryPort`. Testes de
unidade — usam `_FakeRepository` (em memória) via injeção de dependência,
nunca um Postgres real (isso é coberto, à parte, pelos testes de integração
de `test_mcp_server_repository.py`).
"""
from __future__ import annotations

import uuid

import pytest

from src.agents.unified.mcp_config_store import (
    McpServerConfigError,
    add_server,
    delete_server,
    get_server,
    list_servers,
    update_server,
)
from src.application.ports.mcp_server_repository import McpServerRepositoryPort
from src.domain.mcp import McpServerConfig


class _FakeRepository(McpServerRepositoryPort):
    """Repositório em memória — mesma semântica de `PostgresMcpServerRepository`
    (chave `(user_id, name)`), sem tocar Postgres."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], McpServerConfig] = {}

    async def save(self, server: McpServerConfig) -> None:
        self._rows[(server.user_id, server.name)] = server

    async def get(self, user_id: str, name: str) -> McpServerConfig | None:
        return self._rows.get((user_id, name))

    async def list_by_user(self, user_id: str) -> list[McpServerConfig]:
        return [s for (uid, _name), s in self._rows.items() if uid == user_id]

    async def list_all(self) -> list[McpServerConfig]:
        return list(self._rows.values())

    async def delete(self, user_id: str, name: str) -> None:
        self._rows.pop((user_id, name), None)


@pytest.fixture
def repo() -> _FakeRepository:
    return _FakeRepository()


def _user_id() -> str:
    return str(uuid.uuid4())


async def test_list_servers_for_unknown_user_is_empty(repo: _FakeRepository) -> None:
    assert await list_servers(_user_id(), repository=repo) == {}


async def test_add_server_stores_entry_scoped_to_user(repo: _FakeRepository) -> None:
    user_id = _user_id()
    entry = await add_server(
        user_id,
        "meu-servidor",
        command="npx",
        args=["-y", "@some/server"],
        env={"API_KEY": "valor-secreto"},
        repository=repo,
    )
    assert entry["transport"] == "stdio"
    assert entry["command"] == "npx"
    assert entry["env"] == {"API_KEY": "valor-secreto"}

    servers = await list_servers(user_id, repository=repo)
    assert set(servers) == {"meu-servidor"}


async def test_add_server_rejects_duplicate_name_for_same_user(repo: _FakeRepository) -> None:
    """unit-1 (REQ-001): mesmo usuário, mesmo nome duas vezes → erro."""
    user_id = _user_id()
    await add_server(user_id, "zernio", command="cmd", repository=repo)
    with pytest.raises(McpServerConfigError, match="já existe"):
        await add_server(user_id, "zernio", command="cmd", repository=repo)


async def test_add_server_same_name_different_user_does_not_collide(repo: _FakeRepository) -> None:
    """unit-1 (REQ-001): usuários diferentes podem usar o mesmo nome de servidor."""
    user_a = _user_id()
    user_b = _user_id()
    await add_server(user_a, "zernio", command="cmd-a", repository=repo)

    entry_b = await add_server(user_b, "zernio", command="cmd-b", repository=repo)

    assert entry_b["command"] == "cmd-b"


async def test_get_server_returns_none_for_other_users_server(repo: _FakeRepository) -> None:
    """unit-2 (REQ-001): servidor de outro usuário nunca aparece — nem como erro."""
    user_a = _user_id()
    user_b = _user_id()
    await add_server(user_a, "zernio", command="cmd", repository=repo)

    assert await get_server(user_b, "zernio", repository=repo) is None


async def test_update_server_requires_existing_entry(repo: _FakeRepository) -> None:
    with pytest.raises(McpServerConfigError, match="não existe"):
        await update_server(_user_id(), "ghost", command="cmd", repository=repo)


async def test_update_server_replaces_entry(repo: _FakeRepository) -> None:
    user_id = _user_id()
    await add_server(user_id, "srv", command="npx", args=["-y", "a"], repository=repo)
    await update_server(user_id, "srv", command="npx", args=["-y", "b"], repository=repo)

    entry = await get_server(user_id, "srv", repository=repo)
    assert entry is not None
    assert entry["args"] == ["-y", "b"]


async def test_update_server_cannot_edit_other_users_server(repo: _FakeRepository) -> None:
    """REQ-001: `update_server` só enxerga as linhas do próprio `user_id`."""
    user_a = _user_id()
    user_b = _user_id()
    await add_server(user_a, "srv", command="npx", repository=repo)

    with pytest.raises(McpServerConfigError, match="não existe"):
        await update_server(user_b, "srv", command="npx", repository=repo)


async def test_delete_server_is_idempotent(repo: _FakeRepository) -> None:
    user_id = _user_id()
    await add_server(user_id, "srv", command="cmd", repository=repo)
    await delete_server(user_id, "srv", repository=repo)
    assert await get_server(user_id, "srv", repository=repo) is None
    await delete_server(user_id, "srv", repository=repo)  # não deve levantar


async def test_delete_server_does_not_affect_other_users_server(repo: _FakeRepository) -> None:
    """REQ-001: `delete_server` só remove a linha do próprio `user_id`."""
    user_a = _user_id()
    user_b = _user_id()
    await add_server(user_a, "srv", command="cmd-a", repository=repo)
    await add_server(user_b, "srv", command="cmd-b", repository=repo)

    await delete_server(user_a, "srv", repository=repo)

    assert await get_server(user_a, "srv", repository=repo) is None
    assert await get_server(user_b, "srv", repository=repo) is not None


async def test_multiple_servers_coexist_for_same_user(repo: _FakeRepository) -> None:
    user_id = _user_id()
    await add_server(user_id, "a", command="cmd-a", repository=repo)
    await add_server(user_id, "b", command="cmd-b", repository=repo)

    servers = await list_servers(user_id, repository=repo)
    assert set(servers) == {"a", "b"}


async def test_add_server_rejects_normalized_name_collision(
    repo: _FakeRepository,
) -> None:
    """unit-1 (fix-mcp-multi-server-tool-attribution, task-config-1, REQ-011):
    `add_server(user_id, name="search-server")` para um usuário que já tem
    `search_server` cadastrado MUST raise `McpServerConfigError` identifying
    AMBOS os nomes (a colisão pós-normalização é exatamente o que torna o
    par indistinguível na qualificação `mcp__<server>__<tool>` em
    `_qualify_tool_names`, change `fix-mcp-multi-server-tool-attribution`).
    O write MUST não acontecer — a lista de servidores do usuário fica
    inalterada (sem partial write)."""
    user_id = _user_id()
    await add_server(user_id, "search_server", command="cmd", repository=repo)

    with pytest.raises(McpServerConfigError) as excinfo:
        await add_server(
            user_id, "search-server", command="cmd-2", repository=repo
        )

    message = str(excinfo.value)
    assert "search-server" in message
    assert "search_server" in message
    # Sem partial write: o servidor original continua cadastrado com seu
    # `command` original, e o novo não foi persistido.
    servers = await list_servers(user_id, repository=repo)
    assert set(servers) == {"search_server"}
    assert (await get_server(user_id, "search_server", repository=repo))[
        "command"
    ] == "cmd"
    assert await get_server(user_id, "search-server", repository=repo) is None


async def test_add_server_accepts_distinct_normalized_names_for_same_user(
    repo: _FakeRepository,
) -> None:
    """unit-1 (fix-mcp-multi-server-tool-attribution, task-config-2, REQ-011):
    cadastro de dois servidores com nomes que não colidem pós-normalização
    (`zernio` e `opensddrag` — exatamente o cenário "Nomes de servidor
    distintos após normalização são aceitos" do spec) MUST succeed para o
    MESMO `user_id` — false-positive da checagem de unicidade
    pós-normalização quebraria o caso normal de múltiplos servidores
    independentes. Regression check da checagem adicionada por
    `task-config-1`."""
    user_id = _user_id()
    entry_z = await add_server(
        user_id, "zernio", command="cmd-z", repository=repo
    )
    entry_o = await add_server(
        user_id, "opensddrag", command="cmd-o", repository=repo
    )

    assert entry_z["command"] == "cmd-z"
    assert entry_o["command"] == "cmd-o"
    assert set(await list_servers(user_id, repository=repo)) == {
        "zernio",
        "opensddrag",
    }


async def test_update_server_rejects_rename_into_normalized_collision(
    repo: _FakeRepository,
) -> None:
    """unit-2 (fix-mcp-multi-server-tool-attribution, task-config-2, REQ-011):
    `update_server(user_id, name="opensddrag", new_name="zernio-x", ...)`
    para um usuário que já tem `zernio_x` (com underscore) cadastrado MUST
    ser rejeitado com o MESMO erro de colisão pós-normalização do
    `add_server` — e o servidor `opensddrag` MUST continuar cadastrado sob
    o nome original (sem partial write do rename)."""
    user_id = _user_id()
    await add_server(user_id, "opensddrag", command="cmd-o", repository=repo)
    await add_server(user_id, "zernio_x", command="cmd-z", repository=repo)

    with pytest.raises(McpServerConfigError) as excinfo:
        await update_server(
            user_id,
            "opensddrag",
            new_name="zernio-x",
            command="cmd-o-renamed",
            repository=repo,
        )

    message = str(excinfo.value)
    assert "zernio-x" in message
    assert "zernio_x" in message
    # Sem partial write do rename: o `opensddrag` original continua
    # cadastrado com seu `command` original; o `zernio_x` continua
    # inalterado; o nome `zernio-x` (com hífen) nunca foi persistido.
    opensddrag_entry = await get_server(
        user_id, "opensddrag", repository=repo
    )
    assert opensddrag_entry is not None
    assert opensddrag_entry["command"] == "cmd-o"
    zernio_x_entry = await get_server(user_id, "zernio_x", repository=repo)
    assert zernio_x_entry is not None
    assert zernio_x_entry["command"] == "cmd-z"
    assert await get_server(user_id, "zernio-x", repository=repo) is None
    assert set(await list_servers(user_id, repository=repo)) == {
        "opensddrag",
        "zernio_x",
    }


async def test_update_server_accepts_rename_to_non_colliding_name(
    repo: _FakeRepository,
) -> None:
    """unit-2 (fix-mcp-multi-server-tool-attribution, task-config-2, REQ-011):
    regression check — `update_server(user_id, name="opensddrag",
    new_name="opensddrag-v2", ...)` com nenhum outro servidor colidindo
    pós-normalização MUST succeed e MUST mover a entrada para o novo
    nome (a entrada antiga some)."""
    user_id = _user_id()
    await add_server(user_id, "opensddrag", command="cmd-o", repository=repo)

    entry = await update_server(
        user_id,
        "opensddrag",
        new_name="opensddrag-v2",
        command="cmd-o-renamed",
        repository=repo,
    )

    assert entry["command"] == "cmd-o-renamed"
    # Entrada movida: o nome antigo some, o novo nome aparece.
    assert await get_server(user_id, "opensddrag", repository=repo) is None
    assert await get_server(
        user_id, "opensddrag-v2", repository=repo
    ) is not None
    assert set(await list_servers(user_id, repository=repo)) == {
        "opensddrag-v2"
    }
