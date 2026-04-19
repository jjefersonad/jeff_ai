"""PostgreSQL store configuration for Jeff AI.
Provides persistent storage for long-term memory across conversations.
Uses PostgresStore.from_conn_string for proper initialization.
"""

import os
from dotenv import load_dotenv
from langgraph.store.postgres import PostgresStore
from langgraph.store.memory import InMemoryStore

# Carrega variáveis do arquivo .env
load_dotenv()

# PostgreSQL connection string from environment
POSTGRES_URI = os.getenv("POSTGRES_URI", "postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia")

# Session prefix to isolate agent data
SESSION_PREFIX = "jeff_ai_"

# Cache for PostgresStore instance
_postgres_store_instance = None

def create_postgres_store():
    """Create PostgresStore instance using from_conn_string factory.
    
    Returns:
        PostgresStore configured with PostgreSQL connection pool
    """
    global _postgres_store_instance
    
    if _postgres_store_instance is not None:
        return _postgres_store_instance
    
    print(f"Creating PostgreSQL store with URI: {POSTGRES_URI[:30]}...")
    
    try:
        # Use from_conn_string factory method (returns iterator)
        store_iterator = PostgresStore.from_conn_string(POSTGRES_URI)
        
        # Get the store instance from iterator
        # from_conn_string returns an Iterator[PostgresStore], so we use next()
        store = next(store_iterator)
        
        _postgres_store_instance = store
        
        print(f"✓ PostgreSQL store created with session prefix: {SESSION_PREFIX}")
        print(f"✓ Store ready for deep-agents-ui integration")
        
        return store
    except Exception as e:
        print(f"✗ Failed to create PostgresStore: {e}")
        print(f"  Ensure PostgreSQL is running at: {POSTGRES_URI}")
        print(f"  Falling back to InMemoryStore")
        
        # Fallback to InMemoryStore
        _postgres_store_instance = InMemoryStore()
        return _postgres_store_instance

# Create and export store instance
postgres_store = create_postgres_store()

print(f"✓ PostgresStore instance created: {type(postgres_store)}")
print(f"✓ Session prefix: {SESSION_PREFIX}")
print(f"✓ Ready to use with deep-agents-ui and CompositeBackend")