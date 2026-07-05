"""
Custom LangGraph API Server - Open Source Alternative
Compatible with deep-agent-ui
"""

import json
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
import asyncpg
import psycopg2.extras
import yaml

import sys
sys.path.insert(0, '/app')

from dotenv import load_dotenv
load_dotenv('/app/backend/.env')

# Database configuration
DATABASE_URL = "postgresql://jeff_ia:jeff_ia@jeff_ia_postgres:5432/jeff_ia"

# Graph definitions from langgraph.json
GRAPHS = {}


def load_graphs():
    """Load graph definitions from langgraph.json"""
    global GRAPHS
    try:
        with open('/app/backend/langgraph.json', 'r') as f:
            config = yaml.safe_load(f)
            if 'graphs' in config:
                GRAPHS = config['graphs']
    except Exception as e:
        print(f"Warning: Could not load langgraph.json: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_graphs()
    yield


app = FastAPI(title="Jeff AI LangGraph API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection pool
db_pool: asyncpg.Pool = None


async def get_db():
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    return db_pool


# Pydantic Models
class GraphConfig(BaseModel):
    assistant_id: str
    graph_id: str
    config: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class ThreadCreate(BaseModel):
    metadata: dict = Field(default_factory=dict)


class Thread(BaseModel):
    thread_id: str
    created_at: datetime
    updated_at: datetime
    metadata: dict


class RunInput(BaseModel):
    input: dict
    config: Optional[dict] = None
    metadata: Optional[dict] = None


class RunCreate(BaseModel):
    assistant_id: str
    input: dict
    thread_id: Optional[str] = None
    metadata: Optional[dict] = None


class Run(BaseModel):
    run_id: str
    thread_id: str
    assistant_id: str
    input: dict
    output: Optional[dict] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    metadata: dict


class Assistant(BaseModel):
    assistant_id: str
    graph_id: str
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    version: int = 1


# Initialize Database Tables
async def init_db():
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        # Create assistants table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS assistants (
                id SERIAL PRIMARY KEY,
                assistant_id VARCHAR(255) UNIQUE NOT NULL,
                graph_id VARCHAR(255) NOT NULL,
                name VARCHAR(255),
                description TEXT,
                config JSONB DEFAULT '{}',
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Create threads table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                thread_id VARCHAR(255) UNIQUE NOT NULL,
                assistant_id VARCHAR(255),
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Create runs table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id SERIAL PRIMARY KEY,
                run_id VARCHAR(255) UNIQUE NOT NULL,
                thread_id VARCHAR(255) REFERENCES threads(thread_id),
                assistant_id VARCHAR(255) NOT NULL,
                input JSONB,
                output JSONB,
                status VARCHAR(50) DEFAULT 'pending',
                error TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP,
                metadata JSONB DEFAULT '{}'
            )
        """)

        # Create checkpoints table for state persistence
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id SERIAL PRIMARY KEY,
                thread_id VARCHAR(255) NOT NULL,
                checkpoint_id VARCHAR(255) NOT NULL,
                state JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(thread_id, checkpoint_id)
            )
        """)

    await pool.close()
    print("Database initialized")


# Health Check
@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


# Assistants Endpoints
@app.get("/assistants", response_model=list[dict])
async def list_assistants(db=Depends(get_db)):
    """List all assistants"""
    rows = await db.fetch("SELECT * FROM assistants ORDER BY created_at DESC")
    return [dict(row) for row in rows]


@app.post("/assistants", response_model=dict)
async def create_assistant(assistant: GraphConfig, db=Depends(get_db)):
    """Create a new assistant"""
    assistant_id = assistant.assistant_id or str(uuid.uuid4())

    # Register the graph if it exists in our config
    graph_id = assistant.graph_id
    if graph_id not in GRAPHS:
        # Try to load from langgraph.json
        load_graphs()
        if graph_id not in GRAPHS:
            # Create without graph reference - it's a logical assistant
            pass

    await db.execute(
        """
        INSERT INTO assistants (assistant_id, graph_id, name, config, metadata)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (assistant_id) DO UPDATE SET
            graph_id = EXCLUDED.graph_id,
            name = EXCLUDED.name,
            config = EXCLUDED.config,
            metadata = EXCLUDED.metadata,
            updated_at = NOW()
        RETURNING *;
        """,
        assistant_id,
        assistant.graph_id,
        assistant.graph_id,
        json.dumps(assistant.config),
        json.dumps(assistant.metadata)
    )

    return {
        "assistant_id": assistant_id,
        "graph_id": assistant.graph_id,
        "config": assistant.config,
        "metadata": assistant.metadata
    }


@app.get("/assistants/{assistant_id}")
async def get_assistant(assistant_id: str, db=Depends(get_db)):
    """Get assistant by ID"""
    row = await db.fetchrow("SELECT * FROM assistants WHERE assistant_id = $1", assistant_id)
    if not row:
        raise HTTPException(status_code=404, detail="Assistant not found")
    return dict(row)


@app.get("/assistants/{assistant_id}/graph")
async def get_assistant_graph(assistant_id: str, db=Depends(get_db)):
    """Get graph configuration for an assistant"""
    assistant = await get_assistant(assistant_id, db)

    # Try to get graph from langgraph.json
    graph_id = assistant.get('graph_id')
    load_graphs()

    if graph_id and graph_id in GRAPHS:
        # Return the graph definition from langgraph.json
        return {
            "graph_id": graph_id,
            "definition": GRAPHS[graph_id]
        }

    # Return basic structure if no graph defined
    return {
        "graph_id": graph_id or assistant_id,
        "nodes": ["start", "agent", "end"],
        "edges": [["start", "agent"], ["agent", "end"]]
    }


# Threads Endpoints
@app.get("/threads", response_model=list[dict])
async def list_threads(
    assistant_id: Optional[str] = None,
    db=Depends(get_db)
):
    """List threads, optionally filtered by assistant_id"""
    if assistant_id:
        rows = await db.fetch(
            "SELECT * FROM threads WHERE assistant_id = $1 ORDER BY created_at DESC",
            assistant_id
        )
    else:
        rows = await db.fetch("SELECT * FROM threads ORDER BY created_at DESC")

    return [{"thread_id": row["thread_id"], **row} for row in rows]


@app.post("/threads", response_model=dict)
async def create_thread(thread: ThreadCreate, db=Depends(get_db)):
    """Create a new thread"""
    thread_id = str(uuid.uuid4())

    await db.execute(
        "INSERT INTO threads (thread_id, metadata) VALUES ($1, $2)",
        thread_id,
        json.dumps(thread.metadata)
    )

    return {
        "thread_id": thread_id,
        "metadata": thread.metadata,
        "created_at": datetime.utcnow().isoformat()
    }


@app.get("/threads/{thread_id}")
async def get_thread(thread_id: str, db=Depends(get_db)):
    """Get thread by ID"""
    row = await db.fetchrow("SELECT * FROM threads WHERE thread_id = $1", thread_id)
    if not row:
        raise HTTPException(status_code=404, detail="Thread not found")
    return dict(row)


@app.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str, db=Depends(get_db)):
    """Delete a thread and its runs"""
    await db.execute("DELETE FROM runs WHERE thread_id = $1", thread_id)
    await db.execute("DELETE FROM threads WHERE thread_id = $1", thread_id)
    return {"status": "deleted"}


# Runs Endpoints
@app.get("/threads/{thread_id}/runs", response_model=list[dict])
async def list_runs(thread_id: str, db=Depends(get_db)):
    """List runs for a thread"""
    rows = await db.fetch(
        "SELECT * FROM runs WHERE thread_id = $1 ORDER BY created_at DESC",
        thread_id
    )
    return [dict(row) for row in rows]


@app.post("/threads/{thread_id}/runs", response_model=dict)
async def create_run(
    thread_id: str,
    run: RunCreate,
    db=Depends(get_db)
):
    """Execute a run on a thread"""
    import importlib

    # Get the assistant
    assistant = await get_assistant(run.assistant_id, db)

    # Generate run_id
    run_id = str(uuid.uuid4())

    # Create the run record
    await db.execute(
        """
        INSERT INTO runs (run_id, thread_id, assistant_id, input, status, metadata)
        VALUES ($1, $2, $3, $4, 'pending', $5)
        """,
        run_id,
        thread_id,
        run.assistant_id,
        json.dumps(run.input),
        json.dumps(run.metadata or {})
    )

    # Get the graph function from langgraph.json
    load_graphs()
    graph_path = GRAPHS.get(run.assistant_id)

    output = None
    status = "pending"

    try:
        if graph_path:
            # Load the graph dynamically
            module_path, function_name = graph_path.split(":")
            module = importlib.import_module(module_path.replace("/", ".").replace("\\", "."))
            graph_func = getattr(module, function_name)

            # Compile and run the graph
            graph = graph_func()

            # Get or create checkpoint for thread
            checkpoint = await db.fetchrow(
                "SELECT state FROM checkpoints WHERE thread_id = $1 ORDER BY created_at DESC LIMIT 1",
                thread_id
            )
            config = {"configurable": {"thread_id": thread_id}}
            if checkpoint:
                config["configurable"]["checkpoint_id"] = checkpoint["checkpoint_id"]

            # Invoke the graph
            result = graph.invoke(run.input, config=config)
            output = result if isinstance(result, dict) else {"output": str(result)}

            # Save checkpoint
            checkpoint_id = str(uuid.uuid4())
            await db.execute(
                """
                INSERT INTO checkpoints (thread_id, checkpoint_id, state)
                VALUES ($1, $2, $3)
                ON CONFLICT (thread_id, checkpoint_id) DO NOTHING
                """,
                thread_id,
                checkpoint_id,
                json.dumps(output)
            )

            status = "success"
        else:
            # Simple mode: just echo input with assistant response
            output = {
                "output": f"Assistente '{run.assistant_id}' recebeu: {run.input}",
                "agent": "response"
            }
            status = "success"

    except Exception as e:
        status = "error"
        output = {"error": str(e)}

    # Update run record
    await db.execute(
        """
        UPDATE runs SET output = $1, status = $2, completed_at = NOW()
        WHERE run_id = $3
        """,
        json.dumps(output) if output else None,
        status,
        run_id
    )

    # Update thread
    await db.execute(
        "UPDATE threads SET updated_at = NOW() WHERE thread_id = $1",
        thread_id
    )

    return {
        "run_id": run_id,
        "thread_id": thread_id,
        "assistant_id": run.assistant_id,
        "input": run.input,
        "output": output,
        "status": status,
        "created_at": datetime.utcnow().isoformat()
    }


@app.get("/threads/{thread_id}/runs/{run_id}")
async def get_run(thread_id: str, run_id: str, db=Depends(get_db)):
    """Get run status"""
    row = await db.fetchrow(
        "SELECT * FROM runs WHERE run_id = $1 AND thread_id = $2",
        run_id, thread_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return dict(row)


# Graphs Endpoints (simplified)
@app.get("/graphs")
async def list_graphs():
    """List available graphs from langgraph.json"""
    load_graphs()
    return {
        "graphs": [
            {"graph_id": k, "definition": v} for k, v in GRAPHS.items()
        ]
    }


@app.get("/graphs/{graph_id}")
async def get_graph(graph_id: str):
    """Get graph configuration"""
    load_graphs()
    if graph_id not in GRAPHS:
        raise HTTPException(status_code=404, detail="Graph not found")

    return {
        "graph_id": graph_id,
        "definition": GRAPHS[graph_id]
    }


# Search Assistants (for deep-agent-ui compatibility)
@app.post("/assistants/search")
async def search_assistants(db=Depends(get_db)):
    """Search for assistants - returns empty if none exist"""
    rows = await db.fetch("SELECT * FROM assistants ORDER BY created_at DESC LIMIT 10")
    if not rows:
        return {"assistants": []}
    return {"assistants": [dict(row) for row in rows]}


# Initialize database on startup
@app.on_event("startup")
async def startup():
    await init_db()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)