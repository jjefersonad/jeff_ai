"""Intelligent Development Contract Generator - Expert in creating comprehensive, machine-readable development contracts.
This module creates a specialized agent focused on producing a single, structured contract document based on user requests.
"""
import os
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
import asyncio

from deepagents import create_deep_agent
# from deepagents.backends import LocalFileBackend 
from src.models.ollama_model import ollama_model
from src.tools.technical_spec_tools import analyze_architecture, create_database_schema, validate_system_design
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend, FilesystemBackend
from src.agents.prompts.technical_spec_prompt import TECHNICAL_SPEC_WORKFLOW_INSTRUCTIONS, SUBAGENT_DELEGATION_INSTRUCTIONS
from src.mcp.context7_mcp import context7_tools

from langgraph.store.postgres import PostgresStore
from psycopg_pool import ConnectionPool

from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Carrega variáveis do arquivo .env
load_dotenv()


# Configure a pool de conexão (recomendado usar variável de ambiente)
string_conn = os.getenv("POSTGRES_URI", "postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia")

pool = ConnectionPool(
    conninfo=string_conn,
    min_size=2,
    max_size=10,
    timeout=30,
    max_lifetime=1800,
)

# Inicialize o PostgresStore
pg_store = PostgresStore(pool)

PATH_DIR = Path(__file__).parent.parent

print(f"PATH_DIR: {PATH_DIR.resolve()}")

delegate_subagent = {
    "name": "delegate_to_research_agent",
    "description": "Subagente especializado em realizar pesquisas na internet para coletar informações técnicas relevantes para a criação do contrato de desenvolvimento. Ele pode ser acionado para buscar dados atualizados, tendências tecnológicas, melhores práticas e outras informações que possam enriquecer o conteúdo do contrato.",
    "system_prompt": SUBAGENT_DELEGATION_INSTRUCTIONS,
}
subagents = [delegate_subagent]

# Create the agent with the specified model, tools, system prompt, and backend configuration.
agent = create_deep_agent(
    model=ollama_model,
    tools=[
        analyze_architecture,
        create_database_schema,
        validate_system_design,
        # *context7_tools
    ],
    system_prompt=TECHNICAL_SPEC_WORKFLOW_INSTRUCTIONS,
    subagents=subagents,
    skills=["/skills/"],
    backend=CompositeBackend(
        default=StateBackend(),
        routes={
            f"{PATH_DIR.resolve()}": FilesystemBackend(root_dir=PATH_DIR),
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
agent.with_config({"recursion_limit": 100000})

