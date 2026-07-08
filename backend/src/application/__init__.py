"""Camada de APLICAÇÃO — casos de uso e ports.

Responsabilidade: orquestrar o domínio para realizar operações de negócio
observáveis (ex.: gerar documento de requisitos, planejar e gerar imagem sob
aprovação, avançar uma fase SDD). Define os ports (interfaces abstratas) que a
infraestrutura implementa.

Regra da Dependência: pode importar apenas de `domain` e dos ports deste
pacote. NÃO pode importar de `infrastructure`/`composition`, nem frameworks
(`langgraph`, `deepagents`, `langchain_*`, drivers de banco). A direção da
dependência aponta para dentro via inversão (DIP).
"""
