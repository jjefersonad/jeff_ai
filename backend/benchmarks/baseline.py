#!/usr/bin/env python3
"""Baseline do grafo `unified` — mede ANTES de mexer, para poder comparar DEPOIS.

Task `unified-agent-realignment-task-floor-6`. A change vai remover 8 dos 9
subagentes (Fase 3). Sem um baseline, "melhorou" vira opinião: não há como saber
se a remoção ajudou, atrapalhou ou não mudou nada.

Dois blocos de métricas:

**Estáticas** (sem LLM, determinísticas, rodam em CI):
    - tamanho do system prompt
    - tamanho dos schemas das tools (é aqui que mora o inchaço)
    - nº de tools, nº de subagentes
    - ocupação do `num_ctx` ANTES de o usuário dizer qualquer coisa

**De modelo** (exigem o Ollama; lentas):
    - tokens de entrada reais (contados pelo próprio Ollama)
    - latência por turno (p50/p95)
    - acerto de roteamento sobre `eval_set.json` (versionado no repo)

Uso::

    python benchmarks/baseline.py            # só estáticas (rápido)
    python benchmarks/baseline.py --model    # + métricas de modelo (lento)
    python benchmarks/baseline.py --model --json > baseline.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from langchain_core.utils.function_calling import convert_to_openai_tool  # noqa: E402

from src.agents.unified.agent import (  # noqa: E402
    _SYSTEM_PROMPT,
    _UNIFIED_SUBAGENTS,
    _UNIFIED_TOOLS,
)

EVAL_SET = Path(__file__).parent / "eval_set.json"


# --------------------------------------------------------------------------- #
# Métricas estáticas
# --------------------------------------------------------------------------- #
def static_metrics() -> dict[str, Any]:
    """Tudo o que dá para medir sem chamar o modelo."""
    from src.models.ollama_model import ollama_model

    prompt = _SYSTEM_PROMPT
    schemas = [convert_to_openai_tool(t) for t in _UNIFIED_TOOLS]
    schema_json = json.dumps(schemas, ensure_ascii=False)

    # A janela real é o `num_ctx` do ChatOllama — NÃO o que o modelo suporta.
    # O design da `unified-dev-agent` justificou o prompt monolítico com
    # "128K-256K de contexto"; o num_ctx=8192 anula isso.
    num_ctx = getattr(ollama_model, "num_ctx", None)

    # Maiores schemas: onde o orçamento de contexto está sendo gasto.
    por_tool = sorted(
        (
            (s["function"]["name"], len(json.dumps(s, ensure_ascii=False)))
            for s in schemas
        ),
        key=lambda kv: -kv[1],
    )

    return {
        "num_ctx": num_ctx,
        "n_tools": len(_UNIFIED_TOOLS),
        "n_subagents": len(_UNIFIED_SUBAGENTS),
        # Os subagentes do deepagents são dicts, não objetos — `getattr` cairia
        # no `str(s)` e despejaria o system_prompt inteiro no relatório.
        "subagents": [
            s.get("name", "?") if isinstance(s, dict) else getattr(s, "name", "?")
            for s in _UNIFIED_SUBAGENTS
        ],
        "system_prompt_chars": len(prompt),
        "tool_schemas_chars": len(schema_json),
        "top_10_tool_schemas": por_tool[:10],
    }


# --------------------------------------------------------------------------- #
# Métricas de modelo
# --------------------------------------------------------------------------- #
def _called_tools(response: Any) -> list[str]:
    return [tc["name"] for tc in (getattr(response, "tool_calls", None) or [])]


def _score(case: dict, called: list[str]) -> tuple[bool, str]:
    """A rota está certa? Devolve (acertou, motivo)."""
    proibidas = [t for t in called if t in case.get("expected_none", [])]
    if proibidas:
        return False, f"chamou tool PROIBIDA: {proibidas}"

    if case.get("expected_no_tool"):
        return (not called), ("ok" if not called else f"chamou tool sem precisar: {called}")

    esperadas = case.get("expected_any", [])
    if not called:
        return False, "não chamou tool nenhuma (esperava alguma)"
    if any(t in esperadas for t in called):
        return True, "ok"
    return False, f"chamou {called}, esperava alguma de {esperadas}"


def model_metrics() -> dict[str, Any]:
    """Roda o eval set contra o modelo real. Um turno por caso."""
    from src.models.ollama_model import ollama_model

    cases = json.loads(EVAL_SET.read_text(encoding="utf-8"))["cases"]
    bound = ollama_model.bind_tools(_UNIFIED_TOOLS)
    system = SystemMessage(_SYSTEM_PROMPT)

    resultados: list[dict] = []
    latencias: list[float] = []
    entradas: list[int] = []

    for case in cases:
        t0 = time.perf_counter()
        try:
            resp = bound.invoke([system, HumanMessage(case["prompt"])])
        except Exception as exc:  # noqa: BLE001 — o baseline não pode morrer num caso
            resultados.append({"id": case["id"], "erro": str(exc)[:120], "acertou": False})
            continue
        dt = time.perf_counter() - t0

        called = _called_tools(resp)
        acertou, motivo = _score(case, called)
        usage = resp.usage_metadata or {}

        latencias.append(dt)
        if usage.get("input_tokens"):
            entradas.append(usage["input_tokens"])

        resultados.append({
            "id": case["id"],
            "domain": case["domain"],
            "chamou": called,
            "acertou": acertou,
            "motivo": motivo,
            "latencia_s": round(dt, 2),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
        })
        print(f"  {'✅' if acertou else '❌'} {case['id']:22} {called or '(nenhuma)'}", flush=True)

    validos = [r for r in resultados if "erro" not in r]
    acertos = sum(1 for r in validos if r["acertou"])

    def pct(vals: list[float], p: float) -> float:
        if not vals:
            return 0.0
        s = sorted(vals)
        return round(s[min(int(p * len(s)), len(s) - 1)], 2)

    return {
        "modelo": ollama_model.model,
        "n_casos": len(cases),
        "acerto_roteamento": round(acertos / len(validos), 3) if validos else 0.0,
        "acertos": acertos,
        "input_tokens_medio": round(statistics.mean(entradas)) if entradas else None,
        "input_tokens_max": max(entradas) if entradas else None,
        "latencia_p50_s": pct(latencias, 0.50),
        "latencia_p95_s": pct(latencias, 0.95),
        "casos": resultados,
    }


# --------------------------------------------------------------------------- #
def render(estatico: dict, modelo: dict | None) -> str:
    """Formata o relatório do baseline para leitura humana."""
    num_ctx = estatico["num_ctx"] or 0
    out = ["=" * 68, "BASELINE — grafo `unified`", "=" * 68, "", "ESTÁTICO (sem LLM)"]
    out.append(f"  tools registradas .......... {estatico['n_tools']}")
    out.append(f"  subagentes ................. {estatico['n_subagents']}  {estatico['subagents']}")
    out.append(f"  system prompt .............. {estatico['system_prompt_chars']:,} chars")
    out.append(f"  schemas das tools .......... {estatico['tool_schemas_chars']:,} chars")
    out.append(f"  num_ctx (janela REAL) ...... {num_ctx:,} tokens")

    if modelo:
        inp = modelo["input_tokens_medio"] or 0
        out += [
            "",
            "MODELO (medido pelo Ollama)",
            f"  modelo ..................... {modelo['modelo']}",
            f"  input_tokens (médio) ....... {inp:,}",
            f"  input_tokens (máx) ......... {modelo['input_tokens_max']:,}",
            f"  ocupação do num_ctx ........ {100 * inp / num_ctx:.0f}%"
            if num_ctx else "",
            f"  sobra p/ conversa .......... {num_ctx - inp:,} tokens" if num_ctx else "",
            f"  latência p50 / p95 ......... {modelo['latencia_p50_s']}s / {modelo['latencia_p95_s']}s",
            "",
            f"  ACERTO DE ROTEAMENTO ....... {100 * modelo['acerto_roteamento']:.0f}%"
            f"  ({modelo['acertos']}/{modelo['n_casos']})",
        ]
        erradas = [c for c in modelo["casos"] if not c.get("acertou")]
        if erradas:
            out.append("\n  Rotas erradas:")
            for c in erradas:
                out.append(f"    {c['id']:22} {c.get('motivo') or c.get('erro')}")

    out += ["", "  Top schemas (onde o contexto é gasto):"]
    for name, size in estatico["top_10_tool_schemas"][:6]:
        out.append(f"    {name:26} {size:>6,} chars")
    return "\n".join(line for line in out if line != "")


def main() -> int:
    """Ponto de entrada da CLI."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", action="store_true", help="também mede contra o LLM (lento)")
    ap.add_argument("--json", action="store_true", help="saída JSON")
    args = ap.parse_args()

    estatico = static_metrics()
    modelo = None
    if args.model:
        print("Rodando o eval set contra o modelo real...\n", file=sys.stderr)
        modelo = model_metrics()

    if args.json:
        print(json.dumps({"static": estatico, "model": modelo}, ensure_ascii=False, indent=2))
    else:
        print(render(estatico, modelo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
