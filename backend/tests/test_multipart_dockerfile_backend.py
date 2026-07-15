"""Teste de regressão: `POST /api/references` contra o ambiente construído
a partir de `Dockerfile.backend`.

Motivação (change `consolidate-http-routes-langgraph`, task
`test-3`): `python-multipart` é necessário para `UploadFile`/`File(...)`
funcionar dentro do container `langgraph-api`. A dependência só existe no
`.venv` local via transitividade de outras libs; o container real
(`Dockerfile.backend`) precisa dela explicitamente. Este teste constrói a
imagem do backend e exercita o upload multipart dentro dela.

Aceita:
- REQ-002 (custom-http-app): upload multipart funciona contra o ambiente
  construído a partir de `Dockerfile.backend`.
- Falha com mensagem EXPLÍCITA se `python-multipart` estiver ausente, em vez
  de um erro genérico de request.
"""
from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path

import pytest

# 1x1 PNG transparente — passa no `sniff_image_mime` do `reference_store`.
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)

# Nome da tag local usada para o build de teste.
_IMAGE_TAG = "jeff-ai-test-backend:multipart"


def _have_docker() -> bool:
    return shutil.which("docker") is not None


# Marcador para rodar só quando explicitamente solicitado: este teste é
# pesado (constrói a imagem do backend) e não deve rodar no CI padrão sem
# infra de Docker. Quem quiser pode rodar com
# `pytest -m "docker_integration"`.
docker_integration = pytest.mark.docker_integration


# ---------- Teste estático: garante que o Dockerfile pina python-multipart


def test_dockerfile_backend_pins_python_multipart():
    """Garante que `python-multipart` está no `pip install` do Dockerfile.

    Este é o teste "rárido": falha imediatamente (sem build de imagem)
    se alguém remover a linha de `python-multipart` do
    `backend/Dockerfile.backend`. Complementa o teste de integração
    Docker abaixo, que é caro mas mais fiel.
    """
    dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile.backend"
    text = dockerfile.read_text()
    # Aceita tanto `python-multipart==X.Y.Z` quanto formatos sem versão.
    assert "python-multipart" in text, (
        "python-multipart NÃO está em backend/Dockerfile.backend. "
        "POST /api/references (UploadFile) precisa dessa dependência no "
        "container real — sem ela, o upload falha em runtime. "
        "Adicione 'python-multipart==<versão>' à lista de `pip install`."
    )


def test_dockerfile_backend_pins_fastapi():
    """Garante que `fastapi` está no `pip install` do Dockerfile.

    Achado empírico (test-3 da change `consolidate-http-routes-langgraph`):
    a imagem base `langchain/langgraph-api:3.11` traz `starlette` e
    `uvicorn`, mas NÃO `fastapi`. Nosso `webapp.py` e os routers usam
    `fastapi.FastAPI`, `fastapi.APIRouter`, `fastapi.UploadFile`,
    `fastapi.testclient` (em testes) — tudo exige a dependência.
    Sem ela o container sobe, mas o import de `webapp` quebra em
    `langgraph-api` quando ele carrega o `http.app`.

    Verificado em container real construído a partir de
    `Dockerfile.backend` em 2026-07-14.
    """
    dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile.backend"
    text = dockerfile.read_text()
    assert "fastapi" in text, (
        "fastapi NÃO está em backend/Dockerfile.backend. "
        "O `http.app` (webapp.py) instancia `fastapi.FastAPI` e os "
        "routers usam `fastapi.APIRouter`/`UploadFile`/`File`. A imagem "
        "langchain/langgraph-api:3.11 traz starlette/uvicorn mas não "
        "fastapi — sem essa dep, o container não consegue carregar o "
        "http.app. Adicione 'fastapi==<versão>' à lista de `pip install`."
    )


# ---------- Teste de integração: builda a imagem e exercita o upload


@docker_integration
@pytest.mark.skipif(
    not _have_docker(), reason="docker não disponível no host"
)
def test_post_references_multipart_inside_dockerfile_backend_image(
    tmp_path: Path,
):
    """Constrói a imagem do backend e roda o upload multipart dentro dela.

    Fluxo:
    1. `docker build` a partir de `backend/Dockerfile.backend` em uma tag
       local temporária.
    2. `docker run` um snippet Python dentro da imagem que:
       a. Verifica que `python-multipart` está importável (falha com
          mensagem clara caso contrário);
       b. Faz `POST /api/references` via `TestClient` em `webapp.app`,
          apontando `REFERENCES_DIR` para `/tmp/<tmp>/references`;
       c. Imprime `OK <status>` no stdout em caso de sucesso.

    3. O teste passa se (1) o build teve sucesso E (2) o snippet retornou
       `OK` no stdout. Qualquer outra coisa vira AssertionError com a
       mensagem real do docker.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    backend_dir = repo_root / "backend"

    # 1. Builda a imagem a partir do Dockerfile do backend.
    # O contexto do build é a RAIZ do repo (igual ao `docker-compose.yml`):
    # o Dockerfile faz `COPY backend/ /deps/backend/`, então precisa enxergar
    # `backend/` como subdiretório do contexto.
    build = subprocess.run(
        [
            "docker",
            "build",
            "-f",
            "backend/Dockerfile.backend",
            "-t",
            _IMAGE_TAG,
            ".",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=600,  # 10 min — pip install + image pull
    )
    assert build.returncode == 0, (
        f"docker build falhou (rc={build.returncode}).\n"
        f"STDOUT (tail):\n{build.stdout[-2000:]}\n"
        f"STDERR (tail):\n{build.stderr[-2000:]}"
    )

    # 2. Script que roda dentro do container. Aponta REFERENCES_DIR para
    # /tmp para não poluir o filesystem do container. O app FastAPI é
    # carregado por `from src.infrastructure.web.webapp import app`.
    script = r"""
import sys
import tempfile
from pathlib import Path

# Falha EXPLÍCITA se python-multipart não estiver instalado.
try:
    import multipart  # noqa: F401
except ImportError as exc:
    print(
        "FAIL: python-multipart não está instalado neste container. "
        "POST /api/references (UploadFile) precisa dessa dependência. "
        "Adicione 'python-multipart==<versão>' ao pip install de "
        "backend/Dockerfile.backend. "
        f"Erro original: {exc!r}",
        file=sys.stderr,
    )
    sys.exit(2)

import base64
from fastapi.testclient import TestClient

# Aponta REFERENCES_DIR para /tmp via monkeypatch de atributo de módulo.
import src.infrastructure.web.images_router as ir
ref_dir = Path(tempfile.mkdtemp(prefix="ref-"))
ir.REFERENCES_DIR = ref_dir

from src.infrastructure.web.webapp import app  # noqa: E402

# `require_auth` (task-rest-3) agora protege /api/references por padrão;
# este teste cobre python-multipart, não auth, então faz override direto.
from src.infrastructure.auth.dependencies import require_auth  # noqa: E402
from src.infrastructure.auth.users import User  # noqa: E402

app.dependency_overrides[require_auth] = lambda: User(
    id="test", username="test", password_hash="x", role="admin", is_active=True
)

_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)

client = TestClient(app)
resp = client.post(
    "/api/references",
    files={"file": ("x.png", _PNG_1X1, "image/png")},
)
if resp.status_code != 200:
    print(
        f"FAIL: status inesperado: {resp.status_code} {resp.text}",
        file=sys.stderr,
    )
    sys.exit(3)
body = resp.json()
for key in ("path", "url", "filename"):
    if key not in body:
        print(f"FAIL: resposta sem chave {key!r}: {body}", file=sys.stderr)
        sys.exit(4)
print(f"OK {resp.status_code} {body['url']}")
"""

    # 3. Roda o script dentro do container, montado em /tmp/regression-<tmp>
    # para que o snippet possa usar o filesystem do container.
    # IMPORTANTE: o `langchain/langgraph-api:3.11` define um ENTRYPOINT
    # (`/storage/entrypoint.sh`) que inicializa o servidor langgraph mesmo
    # quando passamos outro comando. Precisamos sobrescrevê-lo com
    # `--entrypoint=""` para rodar nosso snippet Python diretamente.
    run = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint=",
            _IMAGE_TAG,
            "python",
            "-c",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    stdout = run.stdout.strip()
    stderr = run.stderr.strip()
    assert run.returncode == 0, (
        f"multipart upload no container falhou (rc={run.returncode}).\n"
        f"STDOUT: {stdout}\n"
        f"STDERR: {stderr}"
    )
    assert stdout.startswith("OK "), (
        f"snippet do container não imprimiu 'OK': {stdout!r}\n"
        f"STDERR: {stderr}"
    )
