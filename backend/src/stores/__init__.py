"""Stores module for Jeff AI.
Contains persistent storage configurations for long-term memory.
"""

from .postgres_store import postgres_store

__all__ = ["postgres_store"]