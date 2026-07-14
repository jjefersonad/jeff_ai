"""Adapter de fetch de imagem de referência via httpx (implementa `ReferenceImageFetchPort`).

Baixa uma imagem de uma URL com defesas contra abuso: só http/https, bloqueio de
hosts privados/loopback (SSRF), limite de tamanho, timeout e validação do formato
por magic bytes. Salva em `outputs/references/` e retorna o caminho local.
"""
from __future__ import annotations

import asyncio
import datetime
import ipaddress
import socket
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

from src.application.ports.reference_image_fetch import (
    ReferenceImageFetchError,
    ReferenceImageFetchPort,
)
from src.infrastructure.media.image_signatures import (
    extension_for_mime,
    sniff_image_mime,
)

_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[3] / "outputs" / "references"
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_DEFAULT_TIMEOUT = 10.0
_ALLOWED_SCHEMES = ("http", "https")


class HttpxReferenceImageFetch(ReferenceImageFetchPort):
    """Busca imagens de referência remotas com validação de segurança."""

    def __init__(
        self,
        *,
        output_dir: Path | None = None,
        max_bytes: int = _DEFAULT_MAX_BYTES,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Configura destino, limites e (opcional) transport injetável para teste."""
        self._output_dir = output_dir or _DEFAULT_OUTPUT_DIR
        self._max_bytes = max_bytes
        self._timeout = timeout
        self._transport = transport

    async def fetch(self, url: str) -> str:
        """Baixa, valida e salva a imagem de `url`; retorna o path local."""
        await self._assert_safe_url(url)
        data = await self._download(url)

        mime_type = sniff_image_mime(data)
        if mime_type is None:
            raise ReferenceImageFetchError(
                f"A URL não retornou uma imagem em formato suportado: {url!r}."
            )

        return self._save(data, mime_type)

    async def _assert_safe_url(self, url: str) -> None:
        """Valida esquema e bloqueia hosts privados/loopback (SSRF)."""
        parsed = urlparse(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            raise ReferenceImageFetchError(
                f"Esquema de URL não permitido: {parsed.scheme!r} (use http/https)."
            )
        if not parsed.hostname:
            raise ReferenceImageFetchError(f"URL sem host válido: {url!r}.")

        try:
            infos = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, None)
        except socket.gaierror as exc:
            raise ReferenceImageFetchError(
                f"Não foi possível resolver o host da URL: {url!r} ({exc})."
            ) from exc

        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                raise ReferenceImageFetchError(
                    f"Host de destino não permitido (privado/loopback): {ip} — SSRF."
                )

    async def _download(self, url: str) -> bytes:
        """Faz o GET com timeout, enforçando o limite de tamanho durante o stream."""
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport, follow_redirects=False
            ) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > self._max_bytes:
                            raise ReferenceImageFetchError(
                                f"Imagem excede o tamanho máximo de {self._max_bytes} bytes."
                            )
                        chunks.append(chunk)
        except httpx.HTTPError as exc:
            raise ReferenceImageFetchError(
                f"Falha ao baixar a imagem de {url!r}: {exc}."
            ) from exc
        return b"".join(chunks)

    def _save(self, data: bytes, mime_type: str) -> str:
        """Persiste os bytes em `outputs/references/` com nome gerado; retorna o path."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        name = f"{self._timestamp()}-{uuid.uuid4().hex[:8]}{extension_for_mime(mime_type)}"
        path = self._output_dir / name
        path.write_bytes(data)
        return str(path)

    @staticmethod
    def _timestamp() -> str:
        return datetime.datetime.now().strftime("%Y%m%d%H%M%S")
