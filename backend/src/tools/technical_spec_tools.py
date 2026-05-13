from pathlib import Path
from langchain_core.tools import tool

@tool
def merge_generated_files(output_dir: str, final_filename: str) -> str:
    """Combina todos os arquivos gerados sequencialmente em um único documento final.
    Use esta ferramenta para consolidar entregas sem sobrecarregar a memória do modelo.
    """
    try:
        base_path = Path(output_dir).resolve()
        if not base_path.exists():
            return f"Erro: O diretório {output_dir} não existe."

        # Busca todos os arquivos no diretório (exceto o próprio arquivo final se ele já existir)
        files = sorted(
            [f for f in base_path.iterdir() if f.is_file() and f.name != final_filename]
        )

        if not files:
            return "Nenhum arquivo encontrado para unificar."

        final_file_path = base_path / final_filename
        
        with open(final_file_path, "w", encoding="utf-8") as outfile:
            for file_path in files:
                outfile.write(f"\n// --- INÍCIO DO ARQUIVO: {file_path.name} ---\n")
                with open(file_path, "r", encoding="utf-8") as infile:
                    outfile.write(infile.read())
                outfile.write(f"\n// --- FIM DO ARQUIVO: {file_path.name} ---\n\n")

        return f"Sucesso! {len(files)} arquivos unificados com sucesso em: {final_file_path}"
    
    except Exception as e:
        return f"Erro ao unificar arquivos: {str(e)}"
