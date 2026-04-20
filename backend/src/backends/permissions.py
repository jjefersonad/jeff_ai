"""Permissions configuration for Jeff AI.
Define file access rules for different paths in the filesystem.

Note: FilesystemPermission might not be available in deepagents 0.3.9.
This is a placeholder for future permission system integration.
"""

# TODO: Check if FilesystemPermission is available in this version
# from deepagents import FilesystemPermission

# For now, define empty permissions until we upgrade deepagents
memory_permissions = []

# Ideal permissions structure (when available):
"""
memory_permissions = [
    FilesystemPermission(
        operations=["read", "write"],
        paths=["/memories/**"],
    ),
    FilesystemPermission(
        operations=["read", "write"],
        paths=["/workspace/src/**/*.py"],
    ),
    FilesystemPermission(
        operations=["read", "write"],
        paths=["/output/**"],
    ),
]
"""