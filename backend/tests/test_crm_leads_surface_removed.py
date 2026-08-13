"""Lead application surface is gone (correct-funil-lead-as-deal-task-backend-cleanup-1).

unit-1: GET /api/crm/leads and POST /api/crm/leads/{id}/convert → 404
unit-2: no Lead type, no lead use cases, no lead methods on the CRM port
"""
from __future__ import annotations

import inspect
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.domain.crm as crm_domain
import src.infrastructure.web.crm_router as crm_router
from src.application.ports.crm_repository import CrmRepositoryPort

_BACKEND_SRC = Path(__file__).resolve().parent.parent / "src"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(crm_router.router)
    return TestClient(app)


def test_get_crm_leads_returns_404() -> None:
    """unit-1: GET /api/crm/leads has no handler."""
    response = _client().get("/api/crm/leads")
    assert response.status_code == 404


def test_post_crm_leads_convert_returns_404() -> None:
    """unit-1: POST /api/crm/leads/{id}/convert has no handler."""
    response = _client().post("/api/crm/leads/any-id/convert")
    assert response.status_code == 404


def test_crm_domain_has_no_lead_type() -> None:
    """unit-2: domain package does not export Lead."""
    assert not hasattr(crm_domain, "Lead")
    assert "Lead" not in crm_domain.__all__


def test_no_lead_use_case_modules() -> None:
    """unit-2: no create/list/convert/preview lead use cases on disk."""
    use_cases = _BACKEND_SRC / "application" / "use_cases"
    lead_modules = sorted(p.name for p in use_cases.glob("*lead*"))
    assert lead_modules == []


def test_crm_repository_port_has_no_lead_methods() -> None:
    """REQ-004: port does not expose lead persistence."""
    lead_methods = [
        name
        for name, _ in inspect.getmembers(CrmRepositoryPort, predicate=callable)
        if "lead" in name.lower()
    ]
    assert lead_methods == []
