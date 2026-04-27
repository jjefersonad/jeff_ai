import json

stakeholders_data = {
    "stakeholders": [
        {
            "id": "corretor",
            "nome": "Corretor de Imoveis",
            "tipo": "ator",
            "papel": "Usuario principal que gerencia alugueis, cadastra imoveis e intermedia relacoes entre proprietario e inquilino",
            "necessidades": [
                "Cadastro e gestao de imoveis",
                "Controle de contratos de locacao",
                "Emissao de boletos e Recibos",
                "Gestao de comissoes",
                "Visualizacao de painel com metricas de negocios"
            ],
            "criteriosSucesso": [
                "Reducao do tempo de gestao administrativa em 50%",
                "Centralizacao de todas informacoes em uma unica plataforma",
                "Automacao de processos de cobranca",
                "Integracao fluida com sistemas de pagamento"
            ]
        },
        {
            "id": "proprietario",
            "nome": "Proprietario de Imoveis",
            "tipo": "ator",
            "papel": "Dono dos imoveis que recebe alugueis e precisa acompanhar rendimento do patrimonio",
            "necessidades": [
                "Visualizacao de saldo e recebiveis",
                "Acompanhamento do status dos alugueis",
                "Relatorios de rendimento",
                "Recebimento pontual dos alugueis",
                "Transparencia nas transacoes"
            ],
            "criteriosSucesso": [
                "Recebimento garantido e pontual dos alugueis",
                "Visibilidade total das receitas",
                "Minimo de inadimplencia",
                "Comunicacao clara com corretor"
            ]
        },
        {
            "id": "inquilino",
            "nome": "Inquilino/Locatario",
            "tipo": "ator",
            "papel": "Pessoa que aluga o imovel e precisa de facilidade para pagar e se comunicar",
            "necessidades": [
                "Pagamento facilitado via PIX/boleto",
                "Visualizacao de historico de pagamentos",
                "Comunicacao com responsavel",
                "Acesso a contrato digital",
                "Opcoes de parcelamento"
            ],
            "criteriosSucesso": [
                "Experiencia de pagamento simples e rapida",
                "Confirmacao imediata de pagamento",
                "Transparencia nos valores",
                "Suporte acessivel"
            ]
        },
        {
            "id": "administradora",
            "nome": "Administradora de Imoveis",
            "tipo": "area",
            "papel": "Empresa que administra multiplos imoveis de diferentes proprietarios",
            "necessidades": [
                "Gestao multi-proprietario",
                "Relatorios consolidados",
                "Rateio de despesas",
                "Automacao contabill"
            ],
            "criteriosSucesso": [
                "Operacionalizacao eficiente em escala",
                "Precisao em rateios e divisoes",
                "Integracao com sistemas contabeis"
            ]
        },
        {
            "id": "sindico",
            "nome": "Sindico de Condominio",
            "tipo": "ator",
            "papel": "Gestor de condominios que pode intermediar alugueis dentro do condominio",
            "necessidades": [
                "Controle de alugueis no condominio",
                "Gestao de garantias",
                "Integracao com gestao condominial"
            ],
            "criteriosSucesso": [
                "Controle sobre occupancy do condominio",
                "Compliance com normas condominiais"
            ]
        },
        {
            "id": "contador",
            "nome": "Contador",
            "tipo": "ator",
            "papel": "Profissional que precisa de dados contabeis e fiscais para declaracao",
            "necessidades": [
                "Exportacao de dados contabeis",
                "Relatorios fiscais",
                "Historico de transacoes",
                "Integracao com sistemas contabeis"
            ],
            "criteriosSucesso": [
                "Dados precisos para declaracao de IR",
                "Facilidade na exportacao",
                "Conformidade fiscal"
            ]
        },
        {
            "id": "asaas",
            "nome": "ASAAS (Gateway de Pagamento)",
            "tipo": "ator",
            "papel": "Sistema externo de processamento de pagamentos via boleto, PIX e cartao",
            "necessidades": [
                "Integracao via API REST",
                "Webhooks para confirmacao de pagamento",
                "Gestao de carteiras e split de pagamentos",
                "Emissao de carnes e boletos customizados"
            ],
            "criteriosSucesso": [
                "Taxas de transacao competitivas",
                "API estavel e bem documentada",
                "SLA de uptime acima de 99.5%",
                "Suporte tecnico responsivo"
            ]
        },
        {
            "id": "mercadopago",
            "nome": "MercadoPago (Gateway de Pagamento)",
            "tipo": "ator",
            "papel": "Sistema externo alternativo de pagamentos com cartao e PIX",
            "necessidades": [
                "Integracao via SDK/API",
                "Checkout transparente",
                "Split de pagamentos",
                "Atendimento ao comprador"
            ],
            "criteriosSucesso": [
                "Diversidade de meios de pagamento",
                "Processamento seguro de cartao",
                "Concorrencia saudavel com ASAAS"
            ]
        },
        {
            "id": "banco",
            "nome": "Instituicao Bancaria",
            "tipo": "ator",
            "papel": "Banco para recebimento de transferencias, Pix e gestao de contas",
            "necessidades": [
                "Integracao com APIs bancarias",
                "Tratamento de webhook de transferencias",
                "Gestao de chaves PIX"
            ],
            "criteriosSucesso": [
                "Transferencias sem falha",
                "Confirmacao em tempo real"
            ]
        },
        {
            "id": "gov",
            "nome": "Governo/Regulador",
            "tipo": "ator",
            "papel": "Orgaos publicos que regulam contratos de locacao e arrecadacao de impostos",
            "necessidades": [
                "Conformidade com legislacao de locacao",
                "Emissao de documentos fiscais validos",
                "Retencao de impostos quando aplicavel"
            ],
            "criteriosSucesso": [
                "Legalidade dos contratos",
                "Emissao de notas fiscais",
                "Conformidade trabalhista"
            ]
        },
        {
            "id": "devteam",
            "nome": "Equipe de Desenvolvimento",
            "tipo": "area",
            "papel": "Time tecnico responsavel por construir e manter o sistema",
            "necessidades": [
                "Documentacao clara das APIs externas",
                "Ambiente de desenvolvimento bem configurado",
                "Acesso a logs e metricas de producao",
                "Ciclos de deploy ageis"
            ],
            "criteriosSucesso": [
                "Deploy frequente sem interrupcoes",
                "Minimo de incidentes em producao",
                "Cobertura de testes acima de 80%"
            ]
        },
        {
            "id": "investidor",
            "nome": "Investidor",
            "tipo": "ator",
            "papel": "Pessoa ou empresa que financia o projeto e espera retorno",
            "necessidades": [
                "KPIs de crescimento",
                "Metricas de retencao",
                "Relatorios financeiros",
                "Visao clara do roadmap"
            ],
            "criteriosSucesso": [
                "ROI positivo no prazo acordado",
                "Escalabilidade do negocio",
                "Retencao de clientes acima de 85%"
            ]
        },
        {
            "id": "suporte",
            "nome": "Equipe de Suporte",
            "tipo": "area",
            "papel": "Time que atende duvidas e problemas dos usuarios",
            "necessidades": [
                "Acesso a dados do cliente",
                "Ferramentas de suporte (chat/email)",
                "Base de conhecimento atualizada",
                "SLA de resposta definido"
            ],
            "criteriosSucesso": [
                "CSAT acima de 4.5/5",
                "Tempo de primeira resposta abaixo de 2h",
                "Resolucao em primeiro contato acima de 70%"
            ]
        }
    ]
}

with open('/outputs/home/jeferson/projetos/IA/jeff_ai/outputs/stakeholders.json', 'w', encoding='utf-8') as f:
    json.dump(stakeholders_data, f, ensure_ascii=False, indent=2)

print("Arquivo salvo com sucesso!")