from pathlib import Path
from langchain_core.tools import tool
import json

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "sdd"
SPECIFY_DIR = Path(__file__).parent.parent.parent / "outputs" / ".specify"

VALID_ARTIFACTS = {
    "constitution": {
        "file": "constitution.md",
        "required_sections": ["Core Principles", "Technology Constraints", "Development Workflow", "Quality Gates"],
    },
    "spec": {
        "file": "spec.md",
        "required_sections": ["Overview", "User Scenarios", "Functional Requirements", "Non-Functional Requirements", "Key Entities"],
    },
    "plan": {
        "file": "plan.md",
        "required_sections": ["Architecture Overview", "Technology Stack", "Component Design", "API Design", "Implementation Phases"],
    },
    "tasks": {
        "file": "tasks.md",
        "required_sections": ["Dependency Graph", "Phase 1:", "Checkpoint"],
    },
    "data-model": {
        "file": "data-model.md",
        "required_sections": ["Entity Relationship Overview", "Entities", "Validation Rules"],
    },
}


@tool
def load_template(template_name: str) -> str:
    """Carrega um template SDD pelo nome e retorna seu conteudo.

    Nomes validos: constitution, spec, plan, tasks, data-model, api-spec
    """
    template_map = {
        "constitution": TEMPLATES_DIR / "constitution-template.md",
        "spec": TEMPLATES_DIR / "spec-template.md",
        "plan": TEMPLATES_DIR / "plan-template.md",
        "tasks": TEMPLATES_DIR / "tasks-template.md",
        "data-model": TEMPLATES_DIR / "data-model-template.md",
        "api-spec": TEMPLATES_DIR / "contracts" / "api-spec-template.json",
    }

    if template_name not in template_map:
        return f"Template '{template_name}' nao encontrado. Disponiveis: {', '.join(template_map.keys())}"

    template_path = template_map[template_name]
    if not template_path.exists():
        return f"Arquivo de template nao encontrado: {template_path}"

    return template_path.read_text(encoding="utf-8")


@tool
def create_feature_directory(feature_name: str, feature_number: str) -> str:
    """Cria a estrutura de diretorios .specify/specs/{NNN-nome}/ para uma nova feature.

    Args:
        feature_name: Nome da feature em kebab-case (ex: 'user-authentication')
        feature_number: Numero sequencial com 3 digitos (ex: '001')
    """
    base_path = SPECIFY_DIR.resolve()
    specs_dir = base_path / "specs"
    memory_dir = base_path / "memory"

    # Ensure base directories exist
    specs_dir.mkdir(parents=True, exist_ok=True)
    memory_dir.mkdir(parents=True, exist_ok=True)

    feature_dir = specs_dir / f"{feature_number}-{feature_name}"
    contracts_dir = feature_dir / "contracts"

    if feature_dir.exists():
        return f"Diretorio da feature ja existe: {feature_dir}"

    feature_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir.mkdir(parents=True, exist_ok=True)

    # Create placeholder files for all artifacts
    artifacts = [
        "spec.md",
        "plan.md",
        "tasks.md",
        "data-model.md",
        "research.md",
        "quickstart.md",
        "contracts/api-spec.json",
    ]

    created = []
    for artifact in artifacts:
        artifact_path = feature_dir / artifact
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            f"# {artifact.replace('.md', '').replace('.json', '')}\n\n"
            f"**Feature:** {feature_name}\n"
            f"**Feature Number:** {feature_number}\n"
            f"**Created:** pending\n\n"
            f"<!-- This artifact will be populated by the SDD agent pipeline. -->\n"
        )
        created.append(str(artifact_path.relative_to(base_path)))

    # Create constitution placeholder if it doesn't exist
    constitution_path = memory_dir / "constitution.md"
    if not constitution_path.exists():
        constitution_path.parent.mkdir(parents=True, exist_ok=True)
        constitution_path.write_text(
            "# Project Constitution\n\n"
            "<!-- This file will be created/updated by the constitution phase. -->\n"
        )

    return (
        f"Estrutura de diretorios criada com sucesso em: {feature_dir}\n"
        f"Arquivos criados ({len(created)}): {', '.join(created)}\n"
        f"Diretorio da constituicao: {memory_dir}"
    )


@tool
def validate_artifact(file_path: str, artifact_type: str) -> str:
    """Valida um artefato SDD contra sua estrutura esperada.

    Args:
        file_path: Caminho absoluto para o arquivo do artefato
        artifact_type: Tipo do artefato (spec, plan, tasks, constitution, data-model)

    Returns:
        Relatorio de validacao JSON com status PASS/FAIL/WARN por secao.
    """
    if artifact_type not in VALID_ARTIFACTS:
        return json.dumps({
            "status": "ERROR",
            "message": f"Tipo de artefato invalido: '{artifact_type}'. Validos: {', '.join(VALID_ARTIFACTS.keys())}",
        }, indent=2, ensure_ascii=False)

    artifact_path = Path(file_path)
    if not artifact_path.exists():
        return json.dumps({
            "status": "FAIL",
            "file": str(artifact_path),
            "message": "Arquivo nao encontrado",
            "checks": [],
        }, indent=2, ensure_ascii=False)

    content = artifact_path.read_text(encoding="utf-8")
    expected = VALID_ARTIFACTS[artifact_type]
    checks = []

    for section in expected["required_sections"]:
        if section.lower() in content.lower():
            checks.append({"section": section, "status": "PASS"})
        else:
            checks.append({"section": section, "status": "FAIL", "message": f"Secao '{section}' nao encontrada"})

    pass_count = sum(1 for c in checks if c["status"] == "PASS")
    fail_count = sum(1 for c in checks if c["status"] == "FAIL")

    if fail_count == 0:
        overall = "PASS"
    elif pass_count == 0:
        overall = "FAIL"
    else:
        overall = "WARN"

    return json.dumps({
        "status": overall,
        "file": str(artifact_path),
        "artifact_type": artifact_type,
        "checks": checks,
        "summary": f"{pass_count}/{len(checks)} secoes presentes, {fail_count} ausentes",
    }, indent=2, ensure_ascii=False)


@tool
def get_sdd_state(feature_dir: str) -> str:
    """Retorna o estado atual de todos os artefatos SDD no diretorio da feature.

    Indica quais fases estao completas e quais artefatos existem.
    """
    feature_path = Path(feature_dir)
    if not feature_path.exists():
        return json.dumps({
            "status": "ERROR",
            "message": f"Diretorio da feature nao encontrado: {feature_dir}",
        }, indent=2, ensure_ascii=False)

    base_path = SPECIFY_DIR.resolve()
    memory_dir = base_path / "memory"

    state = {
        "feature_dir": str(feature_path),
        "phases": {},
    }

    # Check constitution (global, shared across features)
    constitution_path = memory_dir / "constitution.md"
    if constitution_path.exists():
        content = constitution_path.read_text(encoding="utf-8")
        is_populated = "<!-- This file will be created" not in content and len(content) > 100
        state["phases"]["constitution"] = {
            "status": "complete" if is_populated else "placeholder",
            "file": str(constitution_path),
        }
    else:
        state["phases"]["constitution"] = {"status": "missing", "file": str(constitution_path)}

    # Check feature artifacts
    artifacts = {
        "specify": "spec.md",
        "plan": "plan.md",
        "tasks": "tasks.md",
        "data-model": "data-model.md",
        "implement": "tasks.md",
    }

    for phase, filename in artifacts.items():
        artifact_path = feature_path / filename
        if artifact_path.exists():
            content = artifact_path.read_text(encoding="utf-8")
            is_populated = "<!-- This artifact will be populated" not in content and len(content) > 100
            state["phases"][phase] = {
                "status": "complete" if is_populated else "placeholder",
                "file": str(artifact_path),
            }
        else:
            state["phases"][phase] = {"status": "missing", "file": str(artifact_path)}

    # Determine next phase
    phase_order = ["constitution", "specify", "clarify", "plan", "analyze", "tasks", "implement"]
    next_phase = None
    for phase in phase_order:
        phase_state = state["phases"].get(phase, {})
        if phase_state.get("status") in ("missing", "placeholder"):
            next_phase = phase
            break

    state["next_phase"] = next_phase
    state["pipeline_complete"] = next_phase is None

    return json.dumps(state, indent=2, ensure_ascii=False)


@tool
def get_next_feature_number() -> str:
    """Escaneia o diretorio .specify/specs/ e retorna o proximo numero de feature disponivel (3 digitos)."""
    base_path = SPECIFY_DIR.resolve()
    specs_dir = base_path / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)

    existing = []
    for entry in specs_dir.iterdir():
        if entry.is_dir() and entry.name[:3].isdigit():
            existing.append(int(entry.name[:3]))

    next_num = max(existing) + 1 if existing else 1
    return f"{next_num:03d}"
