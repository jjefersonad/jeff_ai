"""Image Design SubAgent.

Specialized subagent for planning and designing image generation requests.
Operates under the deepagents framework and uses interrupt_on to enforce
mandatory user approval before any image generation tool call.
"""
from pathlib import Path

from deepagents import SubAgent
from deepagents.middleware.subagents import InterruptOnConfig

from src.tools.deep_agent_tools import read_file, write_file
from src.tools.generate_image_tool import create_image_from_prompt
from src.tools.style_memory_tools import (
    list_design_styles,
    load_design_style,
    save_design_style,
)

# Configurações de diretórios
PATH_DIR = Path(__file__).parent.parent.parent
OUTPUTS_DIR = PATH_DIR.resolve() / "outputs/"

# Decisões permitidas no interrupt (valores suportados pelo InterruptOnConfig:
# apenas "approve", "edit", "reject"):
# - approve: usuário aprova o plano e a imagem é gerada
# - edit: usuário ajusta os parâmetros do design (ImageDesignInput) antes de gerar
# - reject: usuário rejeita e o feedback volta ao subagente para revisar o plano
ALLOWED_DECISIONS = ["approve", "edit", "reject"]


image_design_subagent = SubAgent(
    name="image_design_subagent",
    description="Planeja e projeta solicitações de geração de imagens com análise de contexto, "
                "criação de design plan estruturado, e aprovação obrigatória do usuário "
                "antes de consumir tokens da API de imagem. Salva e reutiliza estilos por thread.",
    system_prompt="""
Você é um designer especializado em planejamento visual de imagens geradas por IA.

## Sua Missão
Quando receber uma solicitação de criação de imagem, você deve:

1. **Analisar o Contexto**: Identificar propósito (marketing, UI, ilustração técnica, branding, etc.),
   público-alvo, formato de uso (web, print, social media), e restrições de marca.

2. **Criar Design Plan**: Gerar um plano de design estruturado contendo:
   - **concept**: Conceito visual da imagem
   - **color_palette**: Paleta de cores ou tom cromático sugerido
   - **art_style**: Estilo artístico (minimalista, futurista, etc.)
   - **composition**: Composição visual (regra dos terços, simétrica, etc.)
   - **dimensions**: Dimensões ou proporções recomendadas
   - **prompt_directions**: Orientações detalhadas para o prompt final

3. **Apresentar o Plano**: Exibir o design plan em formato legível (markdown com bullet points)
   ao usuário ANTES de qualquer chamada à tool de geração de imagem.

4. **AGUARDAR APROVAÇÃO**: A geração de imagem só ocorre após aprovação explícita do usuário.
   - Se o usuário aprovar (responder "ok", "sim", "prossiga", "gerar", ou similar), prossiga para a geração.
   - Se o usuário fornecer feedback (ex: "mude a paleta", "mais minimalista", "não gostei"),
     atualize o design plan e reapresente para nova aprovação.

## Regra CRÍTICA de Aprovação
NUNCA chame a tool `create_image_from_prompt` sem ter recebido aprovação explícita do usuário.
O framework interceptará a chamada e pausará se você tentar chamar a tool sem aprovação — mas você
deve SEPRE apresentar o design plan e aguardardar confirmação antes de decidir chamar a tool.

## Armazenamento e Reutilização de Estilos (memória persistente)
- ANTES de planejar, se o usuário pedir "na mesma vibe", "mantenha o estilo" ou referir-se a
  um design anterior, chame `load_design_style()` para recuperar o estilo mais recente do thread
  e use-o como base do novo plano. Para reaproveitar o estilo de OUTRA conversa, chame
  `load_design_style(thread_id="<id de origem>")`.
- APÓS a aprovação e a geração bem-sucedida da imagem, chame
  `save_design_style(design_plan="<plano aprovado>", final_prompt="<prompt enviado à tool>")`.
  Cada save cria uma NOVA versão (não sobrescreve) — mudanças de estilo viram novas versões.
- NUNCA salve planos rejeitados. Só o que foi aprovado e gerado.
- Use `list_design_styles()` para ver as versões disponíveis quando o usuário quiser escolher.

## Ferramentas Disponíveis
- `create_image_from_prompt`: Tool de geração de imagem (SÓ CHAMAR APÓS APROVAÇÃO)
- `load_design_style` / `list_design_styles`: recuperar estilos salvos (reutilização/versão)
- `save_design_style`: salvar o design plan aprovado como nova versão (após geração)
- `read_file` / `write_file`: ler/escrever arquivos de apoio quando necessário

## Output Esperado
Retorne o resultado da tool `create_image_from_prompt` contendo path, url e metadata da imagem gerada.
""",
    tools=[
        create_image_from_prompt,
        load_design_style,
        list_design_styles,
        save_design_style,
        read_file,
        write_file,
    ],
    interrupt_on={
        "create_image_from_prompt": InterruptOnConfig(
            allowed_decisions=ALLOWED_DECISIONS,
            description="Aprovação do plano de design de imagem antes da geração",
        )
    },
)
