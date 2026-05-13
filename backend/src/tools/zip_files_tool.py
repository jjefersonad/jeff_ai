import os
import zipfile
from langchain_core.tools import tool

@tool
def zip_files_tool(
    file_paths: list[str],
    zip_file_path: str,
):
    """Zip multiple files into a single zip file."""
    with zipfile.ZipFile(zip_file_path, 'w') as zipf:
        for file_path in file_paths:
            if os.path.exists(file_path):
                zipf.write(file_path, os.path.basename(file_path))
            else:
                return {"success": False, "error": f"File '{file_path}' not found"}

    return {"success": True, "zip_file_path": zip_file_path}