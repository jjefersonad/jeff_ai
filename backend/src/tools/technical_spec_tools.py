"""Tool `merge_generated_files` — adapter fino sobre GenerateRequirementsDocument.

Traduz a interface da tool (diretório + nome do arquivo final) para o caso de uso
de consolidação e formata a mensagem de retorno. NÃO contém regra de negócio
(ordenação/renderização vivem no domínio de requirements).
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from src.composition.dependencies import build_generate_requirements_document


@tool
def merge_generated_files(output_dir: str, final_filename: str) -> str:
    """Combina todos os arquivos gerados sequencialmente em um único documento final.

    Use esta ferramenta para consolidar entregas sem sobrecarregar a memória do modelo.
    """
    try:
        base_path = Path(output_dir).resolve()
        if not base_path.exists():
            return f"Erro: O diretório {output_dir} não existe."

        use_case = build_generate_requirements_document(base_path)
        result = use_case.execute(final_filename)

        if result.section_count == 0:
            return "Nenhum arquivo encontrado para unificar."

        return (
            f"Sucesso! {result.section_count} arquivos unificados com sucesso "
            f"em: {result.path}"
        )
    except Exception as e:  # noqa: BLE001 - mantém o contrato legado de retornar erro como texto
        return f"Erro ao unificar arquivos: {str(e)}"
