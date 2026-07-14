"""Testes de `scripts/wait_for_postgres.py` (pre-flight de `make dev`)."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import wait_for_postgres as wfp  # noqa: E402


class _FakeConnection:
    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def test_wait_for_postgres_success_first_try(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_connect(uri: str, connect_timeout: float) -> _FakeConnection:
        calls.append(uri)
        return _FakeConnection()

    monkeypatch.setattr(wfp.psycopg, "connect", fake_connect)

    assert wfp.wait_for_postgres("postgresql://fake", total_timeout=1, poll_interval=0.01)
    assert len(calls) == 1


def test_wait_for_postgres_success_after_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"n": 0}

    def fake_connect(uri: str, connect_timeout: float) -> _FakeConnection:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise psycopg.OperationalError("connection refused")
        return _FakeConnection()

    monkeypatch.setattr(wfp.psycopg, "connect", fake_connect)

    assert wfp.wait_for_postgres("postgresql://fake", total_timeout=5, poll_interval=0.01)
    assert attempts["n"] == 3


def test_wait_for_postgres_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_connect(uri: str, connect_timeout: float) -> _FakeConnection:
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(wfp.psycopg, "connect", fake_connect)

    assert not wfp.wait_for_postgres("postgresql://fake", total_timeout=0.1, poll_interval=0.02)


def test_main_fails_fast_when_postgres_uri_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("POSTGRES_URI", raising=False)
    monkeypatch.setattr(wfp, "load_dotenv", lambda: None)

    assert wfp.main() == 1
    assert "POSTGRES_URI" in capsys.readouterr().err


def test_main_prints_actionable_message_on_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(wfp, "load_dotenv", lambda: None)
    monkeypatch.setenv("POSTGRES_URI", "postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia")
    monkeypatch.setattr(
        wfp, "wait_for_postgres", lambda uri, **kwargs: False
    )

    assert wfp.main() == 1
    assert "docker compose up -d jeff_ia_postgres" in capsys.readouterr().err


def test_main_succeeds_when_postgres_reachable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(wfp, "load_dotenv", lambda: None)
    monkeypatch.setenv("POSTGRES_URI", "postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia")
    monkeypatch.setattr(wfp, "wait_for_postgres", lambda uri, **kwargs: True)

    assert wfp.main() == 0
    assert "OK" in capsys.readouterr().out
