# Implementation Plan: {feature_name}

**Based on:** SPEC-{NNN}
**Created:** {date}
**Status:** Draft | In Progress | Complete

## Architecture Overview

### System Context
```text
{Text diagram showing how the system fits into the broader context}
[Client] --> [API Gateway] --> [Service Layer] --> [Data Layer]
```

### Technology Stack

| Layer | Technology | Version | Justification |
|-------|------------|---------|---------------|
| Language | {e.g., Python} | {>=3.11} | {Why this language} |
| Framework | {e.g., FastAPI} | {latest} | {Why this framework} |
| Database | {e.g., PostgreSQL} | {16} | {Why this database} |
| Cache | {e.g., Redis} | {7} | {Why caching is needed} |
| Message Queue | {e.g., RabbitMQ} | {3.12} | {Why async messaging} |

## Component Design

### Component: {name}
**Responsibility:** {Single responsibility description}
**Dependencies:** {Other components it depends on}
**Interfaces:** {APIs or contracts it exposes}

### Component: {name}
**Responsibility:** {Single responsibility description}
**Dependencies:** {Other components it depends on}
**Interfaces:** {APIs or contracts it exposes}

## Data Flow

{Text description of how data flows through the system for key operations}

### Example: {Operation Name}
1. {Step 1 of data flow}
2. {Step 2 of data flow}
3. {Step 3 of data flow}

## API Design

| Method | Path | Purpose | Request Body | Response |
|--------|------|---------|-------------|----------|
| GET | /api/{resource} | {purpose} | - | {response schema} |
| POST | /api/{resource} | {purpose} | {request schema} | {response schema} |
| PUT | /api/{resource}/{id} | {purpose} | {request schema} | {response schema} |
| DELETE | /api/{resource}/{id} | {purpose} | - | {response schema} |

## Implementation Phases

### Phase 1: Setup & Foundation
- {Setup and foundational tasks}

### Phase 2: User Story 1 - {title} (P1)
- {Implementation tasks for US1}

### Phase 3: User Story 2 - {title} (P2)
- {Implementation tasks for US2}

### Phase 4: Integration & Polish
- {Integration testing, documentation, performance tuning}

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| {e.g., Third-party API downtime} | Medium | High | {e.g., Circuit breaker + fallback cache} |
| {e.g., Data migration complexity} | High | High | {e.g., Phased rollout with rollback plan} |

## Constitution Compliance

<!-- How this plan aligns with each constitutional principle -->
- **Principle 1:** {How this plan satisfies the principle}
- **Principle 2:** {How this plan satisfies the principle}
- **Principle 3:** {How this plan satisfies the principle}
