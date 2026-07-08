# Makefile — gates de qualidade do backend Jeff AI.
# Rodar a partir de `backend/`. Requer as dev deps: `pip install -e ".[dev]"`.
#
# Gate de ARQUITETURA (Clean Architecture / DDD): `make arch` executa o
# import-linter e FALHA (exit != 0) em qualquer violação da Regra da Dependência.
# É o alvo que um CI remoto deve chamar (ex.: `cd backend && make arch`).

PYTHON ?= python
# Diretório de binários do Python ativo (onde ficam ruff/mypy/pytest/lint-imports
# após `pip install -e ".[dev]"`). Torna os alvos robustos mesmo sem o venv no PATH.
BIN := $(shell $(PYTHON) -c 'import sys, os; print(os.path.dirname(sys.executable))')
# import-linter descobre o pacote `src` a partir do PYTHONPATH.
export PYTHONPATH := .

.PHONY: help arch lint-imports ruff typecheck test lint check

help: ## Lista os alvos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

arch: ## Gate de arquitetura: Regra da Dependência via import-linter (usar no CI)
	$(BIN)/lint-imports

lint-imports: arch ## Alias de `arch`

ruff: ## Linter/formatador (ruff)
	$(BIN)/ruff check .

typecheck: ## Checagem de tipos (mypy)
	$(BIN)/mypy .

test: ## Testes (pytest)
	$(BIN)/pytest

# `lint` = gate de arquitetura (verde hoje). ruff/mypy têm dívida pré-existente e
# são alvos separados até serem saneados; então NÃO entram no gate obrigatório ainda.
lint: arch ## Gate obrigatório atual (arquitetura)

check: arch ruff typecheck test ## Suite completa (pode acusar dívida pré-existente de ruff/mypy)
