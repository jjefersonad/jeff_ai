import os
from pathlib import Path
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore
from dotenv import load_dotenv

load_dotenv()
conninfo = os.getenv("POSTGRES_URI")

# 1. Setup das tabelas (o que você já tem)
with PostgresSaver.from_conn_string(conninfo) as saver:
    saver.setup()

# 2. Setup do Store
with PostgresStore.from_conn_string(conninfo) as store:
    store.setup()