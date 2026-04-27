"""Intelligent Development Contract Generator - Expert in creating comprehensive, machine-readable development contracts.
This module creates a specialized agent focused on producing a single, structured contract document based on user requests.
"""
import os
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
import asyncio

from deepagents import create_deep_agent
from src.models.ollama_model import ollama_model
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend, FilesystemBackend
from src.agents.prompts.technical_spec_prompt import NEW_TECHNICAL_SPEC_WORKFLOW_INSTRUCTIONS
from src.agents.subagents.architecture_subagent import architecture_subagent
from src.agents.subagents.database_subagent_subagent import database_subagent
from src.agents.subagents.validation_subagent import validation_subagent
from src.agents.subagents.delegate_subagent import delegate_subagent

from langgraph.store.postgres import PostgresStore
from psycopg_pool import ConnectionPool

# Carrega variáveis do arquivo .env
load_dotenv()


# Configure a pool de conexão (recomendado usar variável de ambiente)
string_conn = os.getenv("POSTGRES_URI", "postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia")

pool = ConnectionPool(
    conninfo=string_conn,
    min_size=1,      # Garante pelo menos uma conexão aberta
    max_size=20,     # Aumente se o agente fizer muitas chamadas paralelas
    timeout=60.0,    # Tempo máximo de espera por uma conexão do pool (os 30s padrão falharam)
    max_idle=30,     # Fecha conexões ociosas após 30s
    check=ConnectionPool.check_connection, # Verifica se a conexão ainda é válida antes de entregar
)

# Inicialize o PostgresStore
pg_store = PostgresStore(pool)

# Diretório base para o backend
BASE_DIR = Path(__file__).parents[5]
PATH_DIR = BASE_DIR / "conexaoelite" / "ce-rastreadores"

print(f"PATH_DIR: {PATH_DIR}")

subagents = [
    architecture_subagent,
    database_subagent,
    validation_subagent,
    # delegate_subagent,
]

# Create the agent with the specified model, tools, system prompt, and backend configuration.
agent = create_deep_agent(
    model=ollama_model,
    tools=[],
    system_prompt=NEW_TECHNICAL_SPEC_WORKFLOW_INSTRUCTIONS,
    subagents=subagents,
    backend=CompositeBackend(
        default=StateBackend(),
        routes={
            f"{BASE_DIR}": FilesystemBackend(root_dir=BASE_DIR),
            "/memories/": StoreBackend(
                store=pg_store,
                namespace=lambda rt: (
                    rt.server_info.assistant_id,
                ),
            ),
            "/skills/": StoreBackend(
                store=pg_store,
                namespace=lambda rt: (
                    rt.server_info.assistant_id,
                ),
            ),
        },
    ),

)

# agent = agent.with_config({"recursion_limit": 50})
