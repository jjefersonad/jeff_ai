"""Backends module for Jeff AI.
Contains filesystem backend configurations for memory management.
"""

from .memory_backend import memory_backend
from .permissions import memory_permissions

__all__ = ["memory_backend", "memory_permissions"]