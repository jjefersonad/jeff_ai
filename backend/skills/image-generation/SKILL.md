---
name: image-generation
description: Documenta e ensina o uso correto da ferramenta create_image_from_prompt para gerar imagens via Google Gemini API a partir de prompts de texto.
---

# Image Generation Skill

Skill de documentação e tutorial para uso da ferramenta de geração de imagens `create_image_from_prompt`, localizada em `backend/src/tools/generate_image_tool.py`.

## Visão Geral

A tool `create_image_from_prompt` permite gerar imagens a partir de descrições textuais (prompts) em linguagem natural, utilizando a API Google Gemini com o modelo `gemini-2.5-flash-image`. A imagem gerada é salva automaticamente como arquivo PNG no diretório `backend/outputs/images/`.

## Assinatura da Tool

```python
@tool
def create_image_from_prompt(prompt: str) -> str:
    """
    Generates an image from a text prompt using the Google Gemini API and saves it to the specified directory.
    """
```

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|-----------|
| `prompt` | `str` | Sim | Descrição textual em linguagem natural da imagem a ser gerada. Quanto mais detalhado e específico, melhor o resultado. |

### Retorno

| Tipo | Descrição |
|------|-----------|
| `str` | Caminho absoluto do arquivo PNG salvo (ex: `backend/outputs/images/20260101120000.png`). |

## Configuração de Ambiente

Antes de usar a tool, certifique-se de que a variável de ambiente `GOOGLE_API_KEY` está configurada com uma chave válida da Google AI (Gemini API).

```bash
export GOOGLE_API_KEY="sua-chave-aqui"
```

## Exemplos de Uso

### Exemplo 1: Prompt simples

```python
from src.tools.generate_image_tool import create_image_from_prompt

path = create_image_from_prompt.invoke("Um gato astronauta flutuando no espaço")
print(f"Imagem salva em: {path}")
```

### Exemplo 2: Cena detalhada

```python
path = create_image_from_prompt.invoke(
    "Uma paisagem montanhosa ao pôr do sol, com um lago refletindo as cores laranja e roxa do céu, árvores de pinheiro em primeiro plano, estilo fotografia realista, luz dourada suave"
)
```

### Exemplo 3: Estilo artístico

```python
path = create_image_from_prompt.invoke(
    "Retrato de uma mulher com óculos de sol, estilo ilustração vetorial minimalista, cores vibrantes, fundo gradiente azul e rosa, linhas limpas"
)
```

## Limitações e Comportamentos

- **Apenas um parâmetro:** A tool aceita apenas o parâmetro `prompt`. Não há controle direto de dimensões, proporção, seed ou estilo via parâmetros adicionais.
- **Formato fixo:** A saída é sempre um arquivo PNG.
- **Nome do arquivo:** O nome é gerado automaticamente com base no timestamp no formato `YYYYMMDDHHMMSS.png` (ex: `20260705091430.png`).
- **Diretório de saída:** As imagens são salvas em `backend/outputs/images/`. O diretório é criado automaticamente se não existir.
- **Modelo:** Usa o modelo `gemini-2.5-flash-image` da Google Gemini API.

## Troubleshooting

| Problema | Causa provável | Solução |
|----------|---------------|---------|
| Erro de autenticação | `GOOGLE_API_KEY` não configurada ou inválida | Defina a variável de ambiente `GOOGLE_API_KEY` com uma chave válida da Google AI. |
| Diretório de saída não encontrado | O caminho `backend/outputs/images/` não existe | A tool cria o diretório automaticamente. Se houver permissão negada, verifique as permissões do sistema de arquivos. |
| Imagem não gerada / retorno vazio | O modelo pode ter falhado em gerar a imagem para o prompt | Tente reformular o prompt com mais detalhes ou um tema diferente. |

## Referências

- Arquivo da tool: `backend/src/tools/generate_image_tool.py`
- Documentação Google Gemini API: https://ai.google.dev/gemini-api/docs
