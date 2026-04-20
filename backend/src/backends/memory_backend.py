"""Memory backend configuration for Jeff AI.
Creates a CompositeBackend with multiple storage strategies:
- /memories/ → StoreBackend (PostgreSQL persistence)
-L /workspace/ → FilesystemBackend (local project access)
.L /output/ → FilesystemBackend (generated artifacts)

Note: Factory pattern for deepagents 0.3.9 - middleware injects runtime.
"""

from typing import Callable, Optional
from deepagents.backends import (
    CompositeBackend, 
    StateBackend, 
    StoreBackend, 
    FilesystemBackend
)

def memory_backend_factory(runtime) -> CompositeBackend:
    """Factory function to create a CompositeBackend configured for Jeff AI.
    
    Args:
        runtime: Runtime object injected by deepagents middleware
    
    Returns:
        CompositeBackend with the following routing:
        - /memories/* → StoreBackend (PostgreSQL, persistent)
        - /workspace/* → FilesystemBackend (local project files)
        - /output/* → FilesystemBackend (generated artifacts)
        - (default) → StateBackend (ephemeral, per-conversation)
    
    Note: LangGraph API injects PostgreSQL store automatically.
          FilesystemBackend needs only root_dir, not runtime parameter.
    """
    # Namespace factory for StoreBackend
    # Since we're in development without authentication, use "default"
    def default_namespace_factory(rt):
        # In development, use "default" as namespace
        return ("default",)
    
    # Create CompositeBackend (NO runtime parameter in constructor)
    return CompositeBackend(
        default=StateBackend(runtime),  # StateBackend NEEDS runtime
        routes={
            "/memories/": StoreBackend(runtime),  # StoreBackend só aceita runtime
            "/workspace/": FilesystemBackend(
                root_dir="/home/jeferson/projetos/IA/jeff_ai",
                virtual_mode=True
            ),  # FilesystemBackend DOES NOT accept runtime
            "/output/": FilesystemBackend(
                root_dir="/home/jeferson/projetos/IA/jeff_ai",
                virtual_mode=True
            ),
        }
    )

# Export factory function for use with create_deep_agent
memory_backend = memory_backend_factory