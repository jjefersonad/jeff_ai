
// --- INÍCIO DO ARQUIVO: Documento_de_Requisito_Sistema_Gestao_Alugueis_2026-05-12.md ---
# DOCUMENTO DE REQUISITOS
## Sistema de Gestão de Aluguéis

**Versão:** 1.0  
**Data:** 2026-05-12  
**Status:** Aprovado para Desenvolvimento

---

## 1. Introdução e Visão Geral

### 1.1 Purpose

O presente documento de requisitos tem como finalidade especificar de forma detalhada todos os requisitos funcionais e não-funcionais do Sistema de Gestão de Aluguéis, desenvolvido para automatizar e otimizar os processos de cobrança de aluguéis e repasse de valores entre os diferentes atores envolvidos no ecossistema de locação imobiliária.

Este documento serve como referência primária para a equipe de desenvolvimento, garantindo que todos os aspectos do sistema sejam claramente definidos antes do início da implementação. A automação proposta visa reduzir erros manuais, padronizar processos financeiros e proporcionar maior transparência a todos os stakeholders do sistema.

### 1.2 Scope

O Sistema de Gestão de Aluguéis abrange o gerenciamento completo do ciclo de vida de uma locação imobiliária, incluindo as seguintes funcionalidades principais:

- **Cadastro de Imóveis**: Registro e gerenciamento de informações detalhadas de imóveis disponíveis para locação
- **Cadastro de Inquilinos**: Registro e manutenção de dados pessoais e financeiros dos inquilinos
- **Cadastro de Proprietários**: Gerenciamento das informações dos proprietários, incluindo dados bancários
- **Cadastro de Corretores**: Registro e gerenciamento de profissionais responsáveis pela intermediação
- **Gestão de Contratos**: Criação, renovação e encerramento de contratos de locação
- **Cobrança de Aluguéis**: Cálculo automático dos valores devidos, incluindo IPTU e condomínio
- **Geração de Boletos**: Emissão de boletos bancários no padrão FEBRABAN
- **Repasse de Valores**: Cálculo e execução de transferências (TED/DOC) para proprietários
- **OSS (Ordem de Serviço)**: Abertura e acompanhamento de chamados de manutenção

### 1.3 Definitions, Acronyms, and Abbreviations

| Termo | Definição |
|-------|-----------|
| **Inquilino** | Pessoa física ou jurídica que celebra contrato de locação e assume a obrigação do pagamento do aluguel |
| **Proprietário** | Pessoa física ou jurídica detentora do direito de propriedade sobre um imóvel |
| **Corretor** | Profissional habilitado que atua como intermediário na celebração de contratos de locação |
| **Aluguel** | Valor periódico pago pelo inquilino ao proprietário pela utilização do imóvel locado |
| **IPTU** | Imposto Predial e Territorial Urbano — tributo municipal incidente sobre imóveis urbanos |
| **Condomínio** | Conjuntos de rateio mensais pagas pelos condôminos para cobrir despesas comuns |
| **Taxa de Administração** | Percentual do valor do aluguel cobrado pelo corretor como remuneração pela gestão |
| **Boleto** | Título de crédito nominativo para efetivar pagamentos em agências bancárias |
| **TED** | Transferência Eletrônica Disponível — transferência com liquidação no mesmo dia útil |
| **DOC** | Documento de Ordem de Crédito — transferência com liquidação D+1 |
| **OSS** | Ordem de Serviço — registro de solicitação de manutenção relacionada a um imóvel |
| **FEBRABAN** | Federação Brasileira de Bancos — entidade responsável pela padronização de documentos bancários |
| **BACEN** | Banco Central do Brasil — órgão regulador do Sistema Financeiro Nacional |
| **Gateway de Pagamento** | Plataforma Asaas de cobrança que processa pagamentos via cartão de crédito, PIX, boleto bancário e assinatura recorrente. Disponível em: https://www.asaas.com |
| **Webhook** | Mecanismo de comunicação automática que permite ao gateway notificar o sistema sobre eventos em tempo real |
| **Tokenização** | Processo de substituição de dados sensíveis de cartão por tokens não reversíveis para armazenamento seguro |
| **PIX** | Sistema Instantâneo de Pagamentos do BACEN, transferência eletrônica em tempo real disponível 24/7 |
| **Asaas** | Gateway de pagamentos brasileiro com funcionalidades de cobrança, split de pagamentos, marketplace e integração via API REST |
| **Customer (Asaas)** | Cliente criado no Asaas representando o inquilino com dados de cobrança |
| **Cobrança (Asaas)** | Cobrança criada no Asaas associada a um customer, podendo ser boleto, PIX ou cartão |
| **Assinatura (Asaas)** | Cobrança recorrente configurada no Asaas para aluguéis mensais automáticos |
| **Split de Pagamento** | Funcionalidade do Asaas para dividir valores entre a imobiliária e o proprietário |

### 1.4 References

1. **Banco Central do Brasil (BACEN)** - Regulamentação sobre transferências eletrônicas (TED/DOC)
2. **FEBRABAN** - Padrões para emissão de boletos de cobrança
3. **Lei do Inquilinato (Lei nº 8.245/1991)** - Legislação que disciplina as locações de imóveis urbanos
4. **Código de Defesa do Consumidor (Lei nº 8.078/1990)** - Legislação aplicável às relações de consumo
5. **Resolução BACEN nº 3.598/2008** - Regulamentação sobre serviços de pagamento
6. **Padrão CNAB** - Padrão brasileiro para intercâmbio de registros eletrônicos
7. **LGPD (Lei nº 13.709/2018)** - Legislação aplicável à proteção de dados pessoais
8. **PCI-DSS** - Padrão de segurança de dados para cartões de pagamento
9. **BACEN - PIX** - Regulamentação do Sistema Instantâneo de Pagamentos
10. **WhatsApp Business API** - Termos de uso para mensagens comerciais via WhatsApp
11. **Asaas API v3** - Documentação da API do gateway de pagamentos Asaas (https://docs.asaas.com/)

---

## 2. Escopo e Objetivos

### 2.1 Objetivos do Sistema

O Sistema de Gestão de Aluguéis tem como objetivo principal automatizar e centralizar todas as operações financeiras relacionadas à administração de imóveis alugados. Os objetivos específicos incluem:

- **Automatizar emissão de boletos**: Gerar automaticamente boletos bancários para cobrança de aluguéis, com opções de envio por e-mail e SMS
- **Controlar inadimplência**: Implementar mecanismos de acompanhamento de pagamentos e identificação automática de atrasos
- **Calcular comissões**: Estabelecer regras configuráveis para cálculo automático de comissões
- **Gerar relatórios fiscais**: Produzir relatórios contábeis e fiscais exigidos pela legislação
- **Gerenciar repasses**: Controlar e automatizar o processo de repasse aos proprietários

### 2.2 Escopo do Projeto

#### 2.2.1 Módulo de Cadastro
- Cadastro completo de imóveis (dados, endereço, características, fotos)
- Cadastro de proprietários com dados bancários para repasses
- Cadastro de inquilinos com documentos e contatos
- Cadastro de corretores e suas comissões
- Cadastro de contratos de aluguel com vigência e condições

#### 2.2.2 Módulo Financeiro
- Controle de receitas e despesas por imóvel e proprietário
- Lançamento automático de aluguéis conforme contratos
- Controle de encargos (IPTU, condomínio, seguro)
- Cálculo de juros e multas por atraso
- Conciliação bancária automática

#### 2.2.3 Módulo de Cobrança
- Geração automática de boletos bancários (boleto registrado)
- Envio automático de lembretes de vencimento
- Registro de pagamentos com conciliação
- Gestão de acordos e renegociações
- Histórico completo de cobranças por inquilino

#### 2.2.4 Módulo de Repasse
- Cálculo automático de repasses aos proprietários
- Dedução de comissões, impostos e encargos
- Geração de cronograma de repasses
- Liberação condicional de repasses (verificação de quitação)
- Relatório analítico de repasses

#### 2.2.5 Integração Bancária e Pagamentos
- Integração com bancos para geração de boletos (layouts FEBRABAN)
- Integração com gateway de pagamentos Asaas
- Integração com sistemas de pagamento (PIX, cartão de crédito/débito)
- Importação de arquivos de retorno bancário
- Atualização automática de status de pagamentos
- Sistema de notificações multi-canal (e-mail, SMS, WhatsApp, push)

### 2.3 Benefícios Esperados

#### 2.3.1 Eficiência Operacional
- Redução do tempo de trabalho manual em processos de cobrança e repasse
- Automação de tarefas repetitivas (geração de boletos, envio de notificações)
- Centralização das informações em uma única plataforma

#### 2.3.2 Redução de Erros
- Eliminação de erros de cálculo manual de comissões e repasses
- Padronização dos processos com validações automáticas
- Redução de falhas humanas na digitação de dados

#### 2.3.3 Transparência
- Visibilidade total dos fluxos financeiros para todos os stakeholders
- Relatórios detalhados e auditáveis em tempo real
- Rastreabilidade completa de todas as operações

#### 2.3.4 Compliance
- Conformidade com exigências fiscais e tributárias
- Adequação às normas do Banco Central para operações bancárias
- Geração de relatórios para auditorias e fiscalizações

### 2.4 Stakeholders

| Stakeholder | Descrição |
|-------------|-----------|
| **Administradora de Imóveis** | Principal usuário e demandante do sistema |
| **Corretores** | Usuários que acompanham o status dos contratos e comissões |
| **Proprietários** | Visualização de relatórios de receitas e repasses |
| **Inquilinos** | Recebimento de boletos e acompanhamento de pagamentos |
| **Contadores** | Acesso a relatórios contábeis e fiscais |

### 2.5 Limitações e Restrições

**Fora do Escopo:**
- Gestão de compra e venda de imóveis
- Sistemas de portaria e controle de acesso
- Integração com redes sociais

**Restrições Técnicas:**
- Necessidade de conexão com a internet para acesso ao sistema
- Compatibilidade limitada com navegadores antigos

**Restrições de Negócio:**
- Repasses vinculados ao recebimento efetivo dos aluguéis
- Funcionalidades específicas podem variar conforme legislação municipal

---

## 3. Requisitos Funcionais

### 3.1 Módulo de Cadastro

#### RF001: Cadastro de Imóveis

**Descrição:** O sistema deve permitir o cadastro completo de imóveis disponíveis para locação.

**Dados do Imóvel:**
- Endereço completo (logradouro, número, complemento, bairro, cidade, estado, CEP)
- Características físicas (área total, área construída, número de quartos, banheiros, vagas de garagem)
- Valor do aluguel mensal acordado
- Valor do IPTU anual
- Valor do condomínio mensal
- Descrição adicional e fotos do imóvel

**Critérios de Aceite:**
- [ ] O sistema deve validar o formato do CEP informado
- [ ] O sistema deve permitir vincular o imóvel a um proprietário existente
- [ ] O sistema deve calcular automaticamente o valor mensal do IPTU rateado
- [ ] O sistema deve permitir o cadastro de múltiplas fotos por imóvel
- [ ] O sistema deve impedir duplicidade de imóveis com mesmo endereço
- [ ] O sistema deve manter histórico de alterações nos dados do imóvel

---

#### RF002: Cadastro de Proprietários

**Descrição:** O sistema deve permitir o cadastro completo de proprietários de imóveis.

**Dados do Proprietário:**
- Nome completo / Razão social
- CPF / CNPJ
- Endereço completo
- Telefones para contato (mínimo 2)
- E-mail
- Dados bancários para repasse (banco, agência, conta, tipo de conta)

**Critérios de Aceite:**
- [ ] O sistema deve validar o formato do CPF ou CNPJ
- [ ] O sistema deve permitir o cadastro de múltiplas contas bancárias
- [ ] O sistema deve permitir indicar uma conta bancária como padrão
- [ ] O sistema deve permitir vincular múltiplos imóveis a um mesmo proprietário
- [ ] O sistema deve armazenar histórico de alterações nos dados bancários

---

#### RF003: Cadastro de Inquilinos

**Descrição:** O sistema deve permitir o cadastro completo de inquilinos e suas garantias.

**Dados do Inquilino:**
- Nome completo, CPF, Data de nascimento, RG
- Endereço completo, Telefones, E-mail
- Profissão / Empresa empregadora, Renda mensal

**Dados do Fiador/Garantia:**
- Tipo de garantia (fiador, seguro fiança, caução, título de capitalização)
- Dados pessoais do fiador (quando aplicável)

**Critérios de Aceite:**
- [ ] O sistema deve validar o formato do CPF
- [ ] O sistema deve permitir cadastrar múltiplos fiadores/garantias por inquilino
- [ ] O sistema deve armazenar digitalização dos documentos de garantia
- [ ] O sistema deve controlar a vigência das garantias

---

#### RF004: Cadastro de Corretores

**Descrição:** O sistema deve permitir o cadastro de corretores e configuração de suas comissões.

**Critérios de Aceite:**
- [ ] O sistema deve validar o número de registro CRECI
- [ ] O sistema deve permitir configurar taxa de comissão por corretor
- [ ] O sistema deve manter histórico de comissões pagas

---

### 3.2 Módulo Financeiro

#### RF005: Calcular Valor do Aluguel com Encargos

**Descrição:** O sistema deve calcular o valor total do aluguel incluindo encargos.

**Critérios de Aceite:**
- [ ] O sistema deve incluir IPTU rateado mensalmente
- [ ] O sistema deve incluir valor do condomínio
- [ ] O sistema deve exibir breakdown detalhado dos valores

---

#### RF006: Gerar Automaticamente Parcelas do Aluguel

**Descrição:** O sistema deve gerar automaticamente as parcelas mensais do aluguel.

**Critérios de Aceite:**
- [ ] O sistema deve gerar parcelas conforme vigência do contrato
- [ ] O sistema deve respeitar o dia de vencimento configurado
- [ ] O sistema deve numerar as parcelas sequencialmente

---

#### RF007: Calcular Taxa de Administração

**Descrição:** O sistema deve calcular a taxa de administração do corretor sobre o valor bruto do aluguel.

**Critérios de Aceite:**
- [ ] O sistema deve aplicar o percentual configurado por contrato
- [ ] O sistema deve registrar a taxa como despesa do proprietário
- [ ] O padrão deve ser 8%, mas deve ser configurável

---

#### RF008: Calcular Comissão de Intermediação

**Descrição:** O sistema deve calcular a comissão de intermediação devida ao corretor.

**Critérios de Aceite:**
- [ ] O sistema deve calcular sobre o valor do aluguel
- [ ] O sistema deve permitir configuração por imóvel/contrato
- [ ] O sistema deve gerar relatório de comissões a pagar

---

### 3.3 Módulo de Cobrança

#### RF009: Emitir Boletos Bancários (Registrados)

**Descrição:** O sistema deve emitir boletos bancários registrados no padrão FEBRABAN.

**Critérios de Aceite:**
- [ ] O sistema deve gerar boleto com todos os dados do sacado e cedente
- [ ] O sistema deve incluir linha digitável e código de barras
- [ ] O sistema deve enviar boleto por e-mail automaticamente
- [ ] O sistema deve permitir reimpressão do boleto

---

#### RF010: Enviar Lembretes de Vencimento Automático

**Descrição:** O sistema deve enviar lembretes automáticos antes do vencimento.

**Critérios de Aceite:**
- [ ] O sistema deve enviar lembrete 5 dias antes do vencimento
- [ ] O sistema deve enviar por e-mail e SMS (quando configurado)
- [ ] O sistema deve registrar o envio no histórico

---

#### RF011: Registrar Pagamentos Parciais e Integrais

**Descrição:** O sistema deve registrar pagamentos parciais e integrais de aluguéis.

**Critérios de Aceite:**
- [ ] O sistema deve permitir registro de pagamento parcial
- [ ] O sistema deve calcular restante pendente após pagamento parcial
- [ ] O sistema deve Conciliar automaticamente com retorno bancário

---

#### RF012: Identificar Inadimplência e Calcular Juros/Multa

**Descrição:** O sistema deve identificar inadimplência e calcular encargos por atraso.

**Critérios de Aceite:**
- [ ] O sistema deve identificar automaticamente aluguéis em atraso
- [ ] O sistema deve calcular multa de 2% sobre o valor
- [ ] O sistema deve calcular juros de 1% ao mês (proporcional ao dia)

---

### 3.4 Módulo de Repasse

#### RF013: Calcular Valor do Repasse ao Proprietário

**Descrição:** O sistema deve calcular o valor do repasse após deduções.

**Fórmula:**
```
Valor Repasse = Valor Bruto - Taxa Admin - IPTU Rateado - Condomínio - Outras Deduções
```

**Critérios de Aceite:**
- [ ] O sistema deve demonstrar o cálculo detalhado
- [ ] O sistema deve descontar encargos rateados corretamente
- [ ] O sistema deve gerar comprovante do cálculo

---

#### RF014: Gerar Arquivo de Transferência Bancária (TED/DOC)

**Descrição:** O sistema deve gerar arquivos para transferência bancária.

**Critérios de Aceite:**
- [ ] O sistema deve gerar arquivo no formato do banco configurado
- [ ] O sistema deve incluir todos os dados para transferência
- [ ] O sistema deve validar dados bancários antes da geração

---

#### RF015: Registrar Histórico de Repasses

**Descrição:** O sistema deve manter histórico completo de todos os repasses.

**Critérios de Aceite:**
- [ ] O sistema deve registrar data, valor e status de cada repasse
- [ ] O sistema deve permitir consulta por período e proprietário
- [ ] O sistema deve emitir comprovante de transferência

---

### 3.5 Módulo de Relatórios

#### RF016: Relatório de Inadimplência

**Descrição:** O sistema deve gerar relatório detalhado de inadimplência.

**Critérios de Aceite:**
- [ ] Listar todos os aluguéis em atraso com tempo de inadimplência
- [ ] Incluir valor total em aberto
- [ ] Permitir filtros por período, imóvel e proprietário

---

#### RF017: Relatório de Repasses Pendentes/Efetuados

**Descrição:** O sistema deve gerar relatório de repasses.

**Critérios de Aceite:**
- [ ] Separar repasses pendentes e efetuados
- [ ] Incluir datas previstas e realizadas
- [ ] Permitir exportação em PDF e Excel

---

#### RF018: Demonstrativo Mensal para Proprietário

**Descrição:** O sistema deve gerar demonstrativo mensal detalhado para o proprietário.

**Critérios de Aceite:**
- [ ] Incluir bruto recebido, deduções e valor líquido
- [ ] Detalhar cada item deduzido
- [ ] Permitir envio automático por e-mail

---

#### RF019: Integração com Gateway de Pagamentos Asaas

**Descrição:** O sistema deve integrar-se com o gateway de pagamentos **Asaas** para processar cobranças de aluguéis via boleto bancário, PIX e cartão de crédito/débito.

**Dados de Configuração do Asaas:**
- API Key de acesso (produção e sandbox)
- Webhook URL para notificações de pagamento
- ID da Conta Asaas
- Configurações de split (divisão de pagamentos)

**Modalidades de Pagamento:**
- **Boleto Bancário**: Emissão de boleto registrado com vencimento configurável
- **PIX**: Geração de QR Code dinâmico para pagamento instantâneo 24/7
- **Cartão de Crédito**: Parcelamento em até 12x com captura automática
- **Cartão de Débito**: Transação à vista
- **Assinatura Recorrente**: Cobrança automática mensal no dia do vencimento

**Funcionalidades Asaas:**
- Cadastro automático de clientes (Customers)
- Geração de cobranças únicas ou recorrentes
- Split de pagamento (divisão entre imobiliária e proprietário)
- Antecipação de recebíveis
- Estorno e cancelamento de cobranças
- Consulta de status em tempo real
- Webhook para notificações de eventos

**Critérios de Aceite:**
- [ ] O sistema deve armazenar API Key do Asaas com criptografia
- [ ] O sistema deve criar customer no Asaas ao cadastrar inquilino
- [ ] O sistema deve sincronizar dados do customer com Asaas
- [ ] O sistema deve gerar cobrança no Asaas no vencimento do aluguel
- [ ] O sistema deve recuperar e armazenar PDF do boleto gerado
- [ ] O sistema deve gerar QR Code PIX e exibir ao inquilino
- [ ] O sistema deve processar cartão de crédito via própria interface do Asaas (redirect ou embedded)
- [ ] O sistema deve criar assinatura recorrente para aluguéis mensais
- [ ] O sistema deve processar webhooks do Asaas para atualizar status de pagamento
- [ ] O sistema deve configurar split de pagamento para repasses automáticos
- [ ] O sistema deve calcular e registrar taxas do Asaas por transação
- [ ] O sistema deve reconciliar automaticamente pagamentos do Asaas com mensalidades
- [ ] O sistema deve exibir relatório de transações do Asaas (valor, status, taxas)

---

#### RF020: Sistema de Notificação Multi-Canal de Cobrança

**Descrição:** O sistema deve implementar um módulo completo de notificações de cobrança com múltiplos canais de comunicação.

**Canais de Notificação:**
- **E-mail**: Envio de boletos, lembretes, confirmações, demonstrativos
- **SMS**: Lembretes de vencimento, alertas de pagamento, confirmações
- **WhatsApp**: Mensagens automatizadas via API do WhatsApp Business
- **Push Notification**: Notificações via aplicativo mobile
- **Portal do Inquilino**: Notificações in-app no portal web

**Templates de Mensagem:**
- Confirmação de pagamento recebido
- Lembrete de vencimento (5 dias, 3 dias, 1 dia)
- Alerta de atraso (1 dia, 5 dias, 10 dias)
- Cobrança amigável (mensagem personalizada)
- Notificação de negativação
- Confirmação de reajuste de aluguel
- Demonstrativo mensal de encargos

**Regras de Agendamento:**
- Configuração de frequência por canal (ex: SMS apenas uma vez por mês)
- Hierarquia de canais (ex: WhatsApp primeiro, SMS como fallback)
- Horário de envio (evitar enviar fora do horário comercial)
- Rate limiting por canal para evitar bloqueios
- Intelligent routing baseado no histórico de entrega

**Tracking e Monitoramento:**
- Registro de entrega de cada notificação
- Taxa de abertura por canal (e-mail, WhatsApp)
- Falhas de entrega e retentativas automáticas
- Dashboard de métricas de engajamento
- Integração com CRM para histórico completo

**Critérios de Aceite:**
- [ ] O sistema deve permitir criar e editar templates de mensagens
- [ ] O sistema deve suportar variáveis dinâmicas (nome, valor, data, contrato)
- [ ] O sistema deve agendar envios com antecedência configurável
- [ ] O sistema deve implementar fila de processamento para evitar sobrecarga
- [ ] O sistema deve registrar histórico completo de todas as notificações
- [ ] O sistema deve permitir preferências de contato por inquilino
- [ ] O sistema deve enviar confirmação de leitura quando disponível
- [ ] O sistema deve gerar relatórios de efetividade por canal
- [ ] O sistema deve implementar double opt-in para canais automatizados
- [ ] O sistema deve respeitar horário de silêncio (22h às 8h) para notificações não urgentes

---

## 4. Requisitos Não Funcionais

### 4.1 Performance

| ID | Nome | Descrição | Critérios de Aceite |
|----|------|-----------|---------------------|
| **RNF001** | Processamento de Folha de Repasse | Processar folha de repasse em até 30 segundos para até 500 contratos | Processamento para 500 contratos em no máximo 30 segundos |
| **RNF002** | Tempo de Resposta | Tempo de resposta das telas < 3 segundos | Operações padrão com tempo inferior a 3 segundos |

### 4.2 Segurança

| ID | Nome | Descrição | Critérios de Aceite |
|----|------|-----------|---------------------|
| **RNF003** | Autenticação e Criptografia | Autenticação por usuário/senha com criptografia | Uso de hash bcrypt, HTTPS obrigatório, proteção contra força bruta |
| **RNF004** | Perfis de Acesso | Perfis diferenciados (admin, financeiro, visualizar) | Três perfis com permissões específicas |
| **RNF005** | Logs de Auditoria | Logs completos para todas as transações | Registro de usuário, data/hora, ação, dados antes/depois |

### 4.3 Disponibilidade

| ID | Nome | Descrição | Critérios de Aceite |
|----|------|-----------|---------------------|
| **RNF006** | Disponibilidade do Sistema | Sistema disponível 99% do tempo | Downtime máximo de 7h18min por mês |
| **RNF007** | Rotinas de Backup | Backup diário automático | Cópias dos últimos 30 dias em local geograficamente distinto |

### 4.4 Escalabilidade

| ID | Nome | Descrição | Critérios de Aceite |
|----|------|-----------|---------------------|
| **RNF008** | Capacidade de Contratos | Suportar até 10.000 contratos simultâneos | Performance adequada com escalabilidade horizontal |

### 4.5 Compatibilidade

| ID | Nome | Descrição | Critérios de Aceite |
|----|------|-----------|---------------------|
| **RNF009** | Suporte a Browsers | Chrome, Firefox, Edge (últimas 2 versões) | Funcionamento completo sem plugins adicionais |
| **RNF010** | Interface Responsiva | Adaptação a dispositivos móveis | Breakpoints para desktop, tablet e mobile |

### 4.6 Conformidade Legal

| ID | Nome | Descrição | Critérios de Aceite |
|----|------|-----------|---------------------|
| **RNF011** | Compliance LGPD | Conformidade com Lei Geral de Proteção de Dados | Consentimento, exportação, eliminação de dados |
| **RNF012** | Emissão de NFSe | Emissão de Nota Fiscal de Serviço Eletrônica | Integração com portais municipais |
| **RNF013** | Geração de DARF | Geração de DARF para comissões | Cálculo correto de IRRF, código de receita específico |

### 4.7 Integração com Asaas

| ID | Nome | Descrição | Critérios de Aceite |
|----|------|-----------|---------------------|
| **RNF014** | Integração com API do Asaas | Comunicação com API REST do Asaas para todas as operações de cobrança | Autenticação via API Key, versionamento da API v3, rate limiting respeitado, tratamento de erros padronizado |
| **RNF015** | Sincronização de Customers | Criação e atualização automática de customers no Asaas | Cadastro de customer para cada inquilino, atualização de dados quando alterado no sistema, mapeamento entre IDs internos e externos |
| **RNF016** | Geração de Cobranças | Criação de cobranças (boleto, PIX, cartão) via API do Asaas | Preenchimento correto de todos os campos, cálculo de valores com encargos, vencimento conforme contrato |
| **RNF017** | Consulta de Status | Verificação de status de cobranças em tempo real | Consulta via API, atualização automática no sistema, webhook para notificações de pagamento |
| **RNF018** | Cancelamento e Estorno | Gestão de cancelamentos e estornos via API | Solicitação de cancelamento quando necessário, tratamento de webhook de cancelamento, registro de histórico |

### 4.8 Gateway de Pagamentos - Asaas

O gateway de pagamentos utilizado será o **Asaas**, plataforma brasileira que oferece:

- **Boleto Bancário**: Emissão de boletos registrados com registro automático
- **PIX**: Geração de QR Code dinâmico para pagamento instantâneo
- **Cartão de Crédito/Débito**: Processamento de transações via tarjeta
- **Assinatura Recorrente**: Cobranças automáticas mensais
- **Split de Pagamento**: Divisão de valores entre conta principal e subcontas

#### 4.8.1 Requisitos Funcionais da Integração Asaas

| ID | Nome | Descrição | Critérios de Aceite |
|----|------|-----------|---------------------|
| **RNF019** | Configuração do Asaas | O sistema deve permitir configurar credenciais de acesso ao Asaas | Cadastro de API Key, ambiente de produção/sandbox, dados da conta Asaas |
| **RNF020** | Cadastro de Clientes | O sistema deve sincronizar clientes com o Asaas via API | Criar customer no Asaas ao cadastrar inquilino, atualizar dados quando alterado, manter histórico de sincronização |
| **RNF021** | Geração de Boletos | O sistema deve gerar boletos via API do Asaas | Solicitar geração de boleto ao Asaas, recuperar PDF e linha digitável, armazenar dados de referência |
| **RNF022** | Geração de QR Code PIX | O sistema deve gerar QR Code PIX para pagamento | Solicitar criação de pagamento PIX, recuperar imagem do QR Code, exibir no portal do inquilino |
| **RNF023** | Processamento de Cartão | O sistema deve processar pagamentos de cartão de crédito | Tokenização de dados de cartão conforme PCI-DSS, tratamento de situações de falha, registro de comprovante |
| **RNF024** | Configuração de Assinaturas | O sistema deve criar assinaturas recorrentes no Asaas | Configurar periodicidade mensal, definir dia de vencimento, permitir cancelar assinatura |
| **RNF025** | Split de Pagamento | O sistema deve configurar divisão de valores no Asaas | Definir percentuais para imobiliária e proprietário, configurar subcontas no Asaas, validar limites de divisão |
| **RNF026** | Webhooks do Asaas | O sistema deve receber e processar webhooks do Asaas | Implementar endpoint para webhooks, processar eventos de pagamento confirmado, falha de pagamento, cancelamento |
| **RNF027** | Relatório de Transações | O sistema deve exibir relatório consolidado de transações do Asaas | Listar transações por período, status, gateway, valor, taxas cobradas |

### 4.9 Sistema de Notificações de Cobrança

O sistema de notificações de cobrança é responsável por comunicar-se com inquilinos e proprietários através de múltiplos canais, garantindo que todas as informações sobre pagamentos e cobranças sejam transmitidas de forma eficiente e compliance.

#### Requisitos Não Funcionais do Sistema de Notificações

| ID | Nome | Descrição | Critérios de Aceite |
|----|------|-----------|---------------------|
| **RNF028** | Taxa de Entrega | Taxa de entrega de mensagens > 99% | Monitoramento em tempo real, fila de retry com 3 tentativas, dead letter queue |
| **RNF029** | Compliance de Comunicações | Conformidade com regulamentações de comunicação | Opt-out funcional, registro de consentimento, LGPD compliance |
| **RNF030** | Throughput de Notificações | Capacidade de processar até 10.000 notificações/hora | Processamento assíncrono, escalabilidade horizontal, batch processing |

---

## 5. Regras de Negócio e Fluxos

### 5.1 Regras de Negócio

| Código | Descrição |
|--------|-----------|
| **RN001** | O pagamento do aluguel vence no dia acordado entre as partes (tipicamente dia 5 ou 6 de cada mês). |
| **RN002** | Após o vencimento, incidir multa de 2% sobre o valor do aluguel. |
| **RN003** | Após o vencimento, incidir juros de mora de 1% ao mês (proporcional ao dia). |
| **RN004** | A taxa de administração do corretor é calculada sobre o valor bruto do aluguel (padrão 8%). |
| **RN005** | O repasse ao proprietário deve ser realizado em até 5 dias úteis após o recebimento. |
| **RN006** | Em caso de inadimplência superior a 30 dias, o sistema deve gerar alerta gerencial. |
| **RN007** | Descontos podem ser aplicados antes do vencimento, respeitando o limite de 10%. |
| **RN008** | O cálculo do ISS deve observar a alíquota municipal vigente (ex: 5% em SP). |
| **RN009** | O sistema deve processar pagamentos via Asaas com taxa máxima de 5% sobre o valor. |
| **RN010** | Em caso de pagamento via cartão de crédito, o sistema deve verificar cobertura de taxa. |
| **RN011** | Notificações de cobrança devem respeitar horário comercial (8h às 22h). |
| **RN012** | Após 3 tentativas de entrega, o sistema deve diversificar o canal de notificação. |

### 5.2 Fluxo de Cobrança

#### Fase 1: Lembrete Prévio (D-5)
- Sistema identifica aluguéis com vencimento nos próximos 5 dias
- Gera e envia mensagem de lembrete ao locatário contendo: valor, data de vencimento, código de barras

#### Fase 2: Data do Vencimento (D+0)
- Sistema emite boleto de cobrança com encargos devidos
- Boleto fica disponível no portal do locatário
- Inicia contagem de prazo para multa e juros

#### Fase 3: Cobrança Amigável (D+1 a D+10)
- Dia 1: primeiro contato telefônico automatizado
- Dia 3: envio de mensagem de cobrança amigável
- Dia 5: segunda ligação e carta eletrônica
- Dia 7: visita presencial agendada (se aplicável)
- Dia 10: última tentativa de negociação

#### Fase 4: Negativação e Cobrança Extrajudicial (D+11 a D+30)
- Dia 11: inclusão nos serviços de proteção ao crédito
- Dia 15: encaminhamento para cobrança extrajudicial
- Dia 20: elaboração de carta de protesto extrajudicial
- Dia 30: avaliação de evolução do processo

#### Fase 5: Avaliação para Ação Judicial (D+90)
- Reunião do comitê de inadimplência
- Avaliação da viabilidade jurídica e financeira
- Decisão: ação de despejo, acordo ou abater como perda

### 5.3 Fluxo de Repasse

#### Etapa 1: Recebimento do Pagamento
```
Entrada: Confirmação de pagamento via boleto, transferência ou PIX
         │
         ▼
Registra data e hora do recebimento
Atualiza status do contrato para "Quitado"
Gera protocolo de recebimento
```

#### Etapa 2: Abatimento da Taxa de Administração
```
Valor Bruto do Aluguel: R$ 3.500,00
Taxa de Administração (8%): R$ 280,00
                           ─────────────────
Subtotal após taxa: R$ 3.220,00
```

#### Etapa 3: Abatimento dos Encargos Rateados
```
Subtotal após taxa: R$ 3.220,00
IPTU Rateado: R$ 150,00
Condomínio: R$ 350,00
                            ─────────────────
Valor do Repasse: R$ 2.720,00
```

#### Etapa 4: Geração de Transferência
- Sistema gera arquivo de transferência para o banco
- Agenda transferência para até 5 dias úteis

#### Etapa 5: Confirmação do Repasse
- Sistema registra data e hora da transferência
- Envia comprovante ao proprietário
- Atualiza histórico de repasses

---

## 6. Casos de Uso

### UC01 - Manter Imóvel

| **Item** | **Descrição** |
|----------|---------------|
| **ID** | UC01 |
| **Nome** | Manter Imóvel |
| **Ator(es)** | Administrador |
| **Descrição** | Permite ao administrador realizar operações de cadastro, edição, consulta e inativação de imóveis |

**Pré-condições:**
- Administrador autenticado com credenciais válidas

**Fluxo Principal:**
1. Administrador acessa o módulo de gestão de imóveis
2. Sistema exibe listagem de imóveis cadastrados
3. Administrador seleciona a operação desejada
4. Sistema valida informações e persiste os dados
5. Sistema exibe mensagem de sucesso

**Pós-condições:**
- Imóvel cadastrado, atualizado ou inativado no sistema
- Logs de auditoria registrados

---

### UC02 - Manter Proprietário

| **Item** | **Descrição** |
|----------|---------------|
| **ID** | UC02 |
| **Nome** | Manter Proprietário |
| **Ator(es)** | Administrador |
| **Descrição** | Gerencia os dados cadastrais e financeiros dos proprietários |

**Pré-condições:**
- Administrador autenticado

**Fluxo Principal:**
1. Administrador acessa o módulo de proprietários
2. Sistema exibe listagem de proprietários
3. Administrador seleciona a operação desejada
4. Sistema persiste os dados e confirma a operação

**Pós-condições:**
- Cadastro do proprietário disponível para vinculação a imóveis

---

### UC03 - Manter Inquilino

| **Item** | **Descrição** |
|----------|---------------|
| **ID** | UC03 |
| **Nome** | Manter Inquilino |
| **Ator(es)** | Administrador |
| **Descrição** | Permite o cadastro e gestão das informações dos inquilinos e suas garantias |

---

### UC04 - Registrar Contrato

| **Item** | **Descrição** |
|----------|---------------|
| **ID** | UC04 |
| **Nome** | Registrar Contrato |
| **Ator(es)** | Administrador |
| **Descrição** | Associa imóvel, inquilino, proprietário e termos do aluguel |

---

### UC05 - Processar Aluguel Mensal

| **Item** | **Descrição** |
|----------|---------------|
| **ID** | UC05 |
| **Nome** | Processar Aluguel Mensal |
| **Ator(es)** | Sistema (automático) |
| **Descrição** | Calcula valores, emite boletos e registra vencimentos |

---

### UC06 - Registrar Pagamento

| **Item** | **Descrição** |
|----------|---------------|
| **ID** | UC06 |
| **Nome** | Registrar Pagamento |
| **Ator(es)** | Recepção/Administrador |
| **Descrição** | Confirma quitação do aluguel |

---

### UC07 - Gerar Repasse

| **Item** | **Descrição** |
|----------|---------------|
| **ID** | UC07 |
| **Nome** | Gerar Repasse |
| **Ator(es)** | Sistema/Financeiro |
| **Descrição** | Calcula e prepara transferência ao proprietário |

---

### UC08 - Emitir Relatório Mensal

| **Item** | **Descrição** |
|----------|---------------|
| **ID** | UC08 |
| **Nome** | Emitir Relatório Mensal |
| **Ator(es)** | Sistema |
| **Descrição** | Gera demonstrativo para o proprietário |

---

### UC09 - Acompanhar Inadimplência

| **Item** | **Descrição** |
|----------|---------------|
| **ID** | UC09 |
| **Nome** | Acompanhar Inadimplência |
| **Ator(es)** | Financeiro |
| **Descrição** | Monitora pagamentos pendentes |

---

### UC10 - Configurar Taxas

| **Item** | **Descrição** |
|----------|---------------|
| **ID** | UC10 |
| **Nome** | Configurar Taxas |
| **Ator(es)** | Administrador |
| **Descrição** | Define taxas de administração e comissões |

---

## 7. Modelo de Dados

### 7.1 Entidades Principais

#### IMOVEL

| Atributo | Tipo | Descrição |
|----------|------|-----------|
| id | INTEGER (PK) | Identificador único do imóvel |
| endereco | VARCHAR(255) | Endereço completo |
| cep | VARCHAR(10) | Código de endereçamento postal |
| tipo | ENUM | Tipo: `residencial` ou `comercial` |
| valor_aluguel | DECIMAL(10,2) | Valor mensal do aluguel |
| valor_iptu | DECIMAL(10,2) | Valor anual do IPTU |
| valor_condominio | DECIMAL(10,2) | Valor mensal do condomínio |
| status | ENUM | Status: `ativo` ou `inativo` |
| proprietario_id | INTEGER (FK) | Referência ao proprietário |

**Chave Primária:** `id`
**Chaves Estrangeiras:** `proprietario_id` → PROPRIETARIO(id)

---

#### PROPRIETARIO

| Atributo | Tipo | Descrição |
|----------|------|-----------|
| id | INTEGER (PK) | Identificador único |
| nome | VARCHAR(255) | Nome completo ou razão social |
| cpf_cnpj | VARCHAR(20) | CPF ou CNPJ |
| email | VARCHAR(255) | E-mail para contato |
| telefone | VARCHAR(20) | Telefone para contato |
| banco | VARCHAR(50) | Nome do banco |
| agencia | VARCHAR(10) | Número da agência |
| conta | VARCHAR(20) | Número da conta |
| tipo_conta | ENUM | Tipo: `corrente` ou `poupança` |

**Chave Primária:** `id`
**Restrições:** `cpf_cnpj` deve ser único

---

#### INQUILINO

| Atributo | Tipo | Descrição |
|----------|------|-----------|
| id | INTEGER (PK) | Identificador único |
| nome | VARCHAR(255) | Nome completo |
| cpf | VARCHAR(14) | CPF do inquilino |
| email | VARCHAR(255) | E-mail para contato |
| telefone | VARCHAR(20) | Telefone para contato |
| data_nascimento | DATE | Data de nascimento |
| tipo_garantia | ENUM | Tipo: `fiador`, `caução`, `seguro` |
| dados_garantia | JSON | Dados específicos da garantia |

**Chave Primária:** `id`
**Restrições:** `cpf` deve ser único

---

#### CONTRATO

| Atributo | Tipo | Descrição |
|----------|------|-----------|
| id | INTEGER (PK) | Identificador único |
| imovel_id | INTEGER (FK) | Referência ao imóvel |
| inquilino_id | INTEGER (FK) | Referência ao inquilino |
| proprietario_id | INTEGER (FK) | Referência ao proprietário |
| data_inicio | DATE | Data de início |
| data_fim | DATE | Data de término |
| valor_aluguel | DECIMAL(10,2) | Valor mensal do aluguel |
| dia_vencimento | INTEGER | Dia do mês para vencimento (1-31) |
| taxa_admin | DECIMAL(5,2) | Percentual da taxa administrativa (%) |
| status | ENUM | Status: `ativo`, `encerrado`, `rescindido`, `pendente` |

**Chave Primária:** `id`
**Chaves Estrangeiras:**
- `imovel_id` → IMOVEL(id)
- `inquilino_id` → INQUILINO(id)
- `proprietario_id` → PROPRIETARIO(id)

---

#### BOLETO

| Atributo | Tipo | Descrição |
|----------|------|-----------|
| id | INTEGER (PK) | Identificador único |
| contrato_id | INTEGER (FK) | Referência ao contrato |
| mes_referencia | VARCHAR(7) | Mês de referência (AAAA-MM) |
| data_vencimento | DATE | Data de vencimento |
| valor_bruto | DECIMAL(10,2) | Valor bruto do aluguel |
| valor_desconto | DECIMAL(10,2) | Valor do desconto aplicado |
| valor_juros | DECIMAL(10,2) | Valor dos juros de mora |
| valor_multa | DECIMAL(10,2) | Valor da multa |
| valor_liquido | DECIMAL(10,2) | Valor líquido a pagar |
| status_pagamento | ENUM | Status: `pendente`, `pago`, `vencido`, `cancelado` |
| data_pagamento | DATETIME | Data e hora do pagamento |
| asaas_id | VARCHAR(50) | ID da cobrança no Asaas |
| asaas_status | VARCHAR(20) | Status da cobrança no Asaas |
| asaas_pdf_url | VARCHAR(255) | URL do PDF do boleto |
| pix_qrcode | TEXT | QR Code PIX em base64 |

**Chave Primária:** `id`
**Chaves Estrangeiras:** `contrato_id` → CONTRATO(id)

---

#### REPASSE

| Atributo | Tipo | Descrição |
|----------|------|-----------|
| id | INTEGER (PK) | Identificador único |
| contrato_id | INTEGER (FK) | Referência ao contrato |
| data_repasse | DATE | Data do repasse |
| valor_bruto_aluguel | DECIMAL(10,2) | Valor bruto do aluguel |
| taxa_admin | DECIMAL(10,2) | Valor da taxa de administração |
| valor_encargos | DECIMAL(10,2) | Valor dos encargos (IPTU, condomínio) |
| valor_repasse | DECIMAL(10,2) | Valor líquido do repasse |
| data_pagamento_proprietario | DATE | Data do pagamento ao proprietário |
| status | ENUM | Status: `pendente`, `processando`, `efetuado`, `falhou` |
| observaciones | TEXT | Observações adicionais |

**Chave Primária:** `id`
**Chaves Estrangeiras:** `contrato_id` → CONTRATO(id)

---

#### USUARIO

| Atributo | Tipo | Descrição |
|----------|------|-----------|
| id | INTEGER (PK) | Identificador único |
| nome | VARCHAR(255) | Nome completo |
| email | VARCHAR(255) | E-mail (login) |
| senha_hash | VARCHAR(255) | Hash da senha |
| perfil | ENUM | Perfil: `admin`, `financeiro`, `visualizador` |
| status | ENUM | Status: `ativo`, `inativo` |
| ultimo_login | DATETIME | Data e hora do último login |

**Chave Primária:** `id`
**Restrições:** `email` deve ser único

---

### 7.2 Relacionamentos

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   IMOVEL    │       │  CONTRATO   │       │  INQUILINO  │
├─────────────┤       ├─────────────┤       ├─────────────┤
│ id (PK)     │◄──────│ imovel_id   │       │ id (PK)     │
│ proprietario│       │ inquilino_id│──────►│             │
│ _id (FK)    │       │ proprietario│       │             │
└─────────────┘       │ _id (FK)    │       └─────────────┘
                      │             │
                      │             │
                      └──────┬──────┘
                             │
                      ┌──────┴──────┐
                      │   BOLETO    │
                      ├─────────────┤
                      │ id (PK)     │
                      │ contrato_id │
                      │ (FK)        │
                      └─────────────┘

┌─────────────┐
│  REPASSE    │
├─────────────┤
│ id (PK)     │
│ contrato_id │
│ (FK)        │
└─────────────┘
```

### 7.3 Restrições de Integridade

**Restrições de Entidade:**
- `cpf` e `cpf_cnpj` devem ser únicos no sistema
- `email` do usuário deve ser único
- Endereço do imóvel não pode estar duplicado

**Restrições de Domínio:**
- `valor_aluguel`, `valor_iptu`, `valor_condominio` devem ser valores positivos
- `taxa_admin` deve estar entre 0 e 100
- `dia_vencimento` deve estar entre 1 e 31

**Restrições de Relacionamento:**
- Ao excluir um proprietário, verificar se existem imóveis vinculados
- Ao excluir um inquilino, verificar se existem contratos ativos
- Ao encerrar um contrato, manter histórico de repasses

---

## 8. Anexos

### 8.1 Glossário Adicional

| Termo | Definição |
|-------|-----------|
| **Chargeback** | Estorno de transação de cartão de crédito solicitado pelo portador do cartão |
| **Conciliação Bancária** | Processo de confronto entre registros financeiros do sistema e extratos bancarios |
| **Cedente** | Beneficiária do título de crédito (imobiliária) |
| **Sacado** | Devedor/pagador do título (inquilino) |
| **Liquidção** | Confirmation do pagamento de um título |
| **Protesto** | Ato cartorial de formalização da inadimplência |
| **Negativação** | Inclusão do devedor em cadastros de proteção ao crédito (Serasa, SPC) |

### 8.2 Padrões de Comunicação

**E-mail:**
- Protocolo: SMTP/IMAP
- Formato: HTML com templates responsivos
- Anexos: PDF de boletos, demonstrativos

**SMS:**
- Provedor: API de SMS (ex: Twilio, Zenvia)
- Limite de caracteres: 160
- Opt-out: Link de descadastro obrigatório

**WhatsApp:**
- API: WhatsApp Business API
- Templates: Pré-aprovados pelo WhatsApp
- HSM: Highly Structured Messages

**Webhook Asaas:**
- Endpoint: `https://api.suaaplicacao.com/webhooks/asaas`
- Métodos: POST
- Autenticação: HMAC-SHA256 signature
- Eventos: `PAYMENT_CONFIRMED`, `PAYMENT_RECEIVED`, `PAYMENT_DELETED`

---

**Documento elaborado em:** 2026-05-12  
**Última atualização:** 2026-05-12  
**Versão:** 1.0
// --- FIM DO ARQUIVO: Documento_de_Requisito_Sistema_Gestao_Alugueis_2026-05-12.md ---

