"""
Intelligent Development Contract Generator (STABLE PIPELINE)

FOCO:
- zero contexto acumulado no LLM
- file-first architecture
- pipeline determinístico
- isolamento total entre etapas
- prevenção de crash do Ollama/httpx
"""

import os
from dotenv import load_dotenv
from pathlib import Path

from deepagents import create_deep_agent

from src.models.ollama_model import ollama_model
from deepagents.backends import (
    CompositeBackend,
    StateBackend,
    StoreBackend,
    FilesystemBackend
)

from langgraph.store.postgres import PostgresStore
from psycopg_pool import ConnectionPool

from pydantic import BaseModel
from typing import List


# =========================
# ENV
# =========================
load_dotenv()

# =========================
# POSTGRES (MEMÓRIA OPCIONAL, NÃO CRÍTICA)
# =========================
string_conn = os.getenv(
    "POSTGRES_URI",
    "postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia"
)

pool = ConnectionPool(
    conninfo=string_conn,
    min_size=1,
    max_size=10,
    timeout=60.0,
    max_idle=30,
    check=ConnectionPool.check_connection,
)

pg_store = PostgresStore(pool)


# =========================
# PATHS
# =========================
BASE_DIR = Path(__file__).parents[3]
OUTPUT_DIR = BASE_DIR.resolve() / "outputs"
print(f"OUTPUT_DIR: {OUTPUT_DIR}")

# =========================
# STATE ULTRA-COMPACTO
# =========================
class CompactState(BaseModel):
    key_points: List[str]
    decisions: List[str]
    open_questions: List[str]


class StepValidation(BaseModel):
    ok: bool
    issues: List[str] = []


class FinalValidation(BaseModel):
    is_complete: bool
    issues: List[str] = []


from deepagents.backends import FilesystemBackend
from pathlib import Path

def filesystem_backend_factory(rt):
    thread_id = rt.config["configurable"]["thread_id"]

    base = OUTPUT_DIR / thread_id
    base.mkdir(parents=True, exist_ok=True)

    return FilesystemBackend(
        root_dir=str(base),
        virtual_mode=True
    )

# =========================
# SUBAGENTS (ISOLADOS)
# =========================

subagents = [

    # -------------------------
    # CONTEXT
    # -------------------------
    {
        "name": "context-analyzer",
        "description": "Extract business context and persist file",
        "system_prompt": """
You are a CONTEXT EXTRACTOR.

TASK:
1. Extract business context
2. Write ONLY:
   /outputs/business_context.md
3. Return ONLY CompactState

RULES:
- do NOT include full explanation
- do NOT repeat prompt
- do NOT generate other files
""",
        "response_format": CompactState
    },

    # -------------------------
    # REQUIREMENTS
    # -------------------------
    {
        "name": "requirements-elicitor",
        "description": "Generate requirements and persist file",
        "system_prompt": """
You are a REQUIREMENTS ENGINE.

TASK:
1. Generate functional + non-functional requirements
2. Write ONLY:
   /outputs/requirements.md
3. Return ONLY CompactState

RULES:
- keep minimal reasoning
- no duplication
""",
        "response_format": CompactState
    },

    # -------------------------
    # STAKEHOLDERS
    # -------------------------
    {
        "name": "stakeholder-mapper",
        "description": "Map stakeholders and persist file",
        "system_prompt": """
You are a STAKEHOLDER ANALYZER.

TASK:
1. Identify stakeholders
2. Write ONLY:
   /outputs/stakeholders.md
3. Return ONLY CompactState
""",
        "response_format": CompactState
    },

    # -------------------------
    # STRUCTURE
    # -------------------------
    {
        "name": "requirements-structurer",
        "description": "Create user stories + AC",
        "system_prompt": """
You are a STRUCTURE ENGINE.

TASK:
1. Create:
   - user_stories.md
   - acceptance_criteria.md

2. Write files directly to /outputs/

3. Return ONLY CompactState
""",
        "response_format": CompactState
    },

    # -------------------------
    # FINAL VALIDATION + INDEX
    # -------------------------
    {
        "name": "final-validator",
        "description": "Validate artifacts and generate index",
        "system_prompt": """
You are a VALIDATION ENGINE.

TASK:
1. Read ALL files in /outputs/
2. Validate consistency
3. Generate ONLY:
   /outputs/index.json

INDEX MUST CONTAIN:
- project summary (short)
- list of files
- keywords per file
- dependency graph (simple)

RULES:
- DO NOT regenerate content
- DO NOT rewrite documents
- ONLY validate + index
""",
        "response_format": FinalValidation
    }
]


# =========================
# AGENT ORCHESTRATOR
# =========================

agent = create_deep_agent(
    model=ollama_model,

    tools=[],  # tools ficam implícitas no deepagents backend

    system_prompt="""
YOU ARE A PIPELINE ORCHESTRATOR.

CRITICAL DESIGN PRINCIPLES:

1. NO CONTEXT ACCUMULATION
2. FILE-FIRST ARCHITECTURE
3. STEP ISOLATION (ONE TASK = ONE OUTPUT)
4. NO LARGE PROMPTS
5. NO CROSS-STEP MEMORY RELIANCE

WORKFLOW:

- Step 1: context-analyzer
- Step 2: requirements-elicitor
- Step 3: stakeholder-mapper
- Step 4: requirements-structurer
- Step 5: final-validator

RULES:

✔ always start with write_todos
✔ never pass full documents between steps
✔ only CompactState is shared
✔ every step MUST write file immediately
✔ final step ONLY creates index.json

ANTI-FAILURE STRATEGY:

- no long chains of reasoning
- no large JSON outputs
- no streaming dependency on full response
- avoid Ollama overload
""",

    subagents=subagents,
    backend=CompositeBackend(
        default=StateBackend(),

        routes={
            "/outputs/": filesystem_backend_factory,
            "/memories/": StoreBackend(
                store=pg_store,
                namespace=lambda rt: (
                    rt.server_info.assistant_id,
                ),
            )
        },
    ),
)


# =========================
# CONFIG DE EXECUÇÃO
# =========================
agent = agent.with_config({
    "recursion_limit": 8,
    "max_concurrency": 1
})