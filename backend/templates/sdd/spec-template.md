# Feature Specification: {feature_name}

**Feature ID:** SPEC-{NNN}
**Created:** {date}
**Status:** Draft | Review | Approved
**Input:** {user_request_summary}

## Overview

### Problem Statement
{1-2 paragraphs describing the problem being solved and why it matters}

### Proposed Solution
{High-level description of WHAT will be built. Do NOT describe HOW or mention technologies.}

### Success Criteria
- [ ] {Measurable outcome 1}
- [ ] {Measurable outcome 2}
- [ ] {Measurable outcome 3}

## User Scenarios & Testing

### User Story 1 - {title} (Priority: P1)

**As a** {role},
**I want** {action},
**So that** {benefit}.

**Acceptance Criteria:**
- [ ] Given {precondition}, when {action}, then {expected result}
- [ ] Given {precondition}, when {action}, then {expected result}

### User Story 2 - {title} (Priority: P2)

**As a** {role},
**I want** {action},
**So that** {benefit}.

**Acceptance Criteria:**
- [ ] Given {precondition}, when {action}, then {expected result}

### User Story 3 - {title} (Priority: P3)

**As a** {role},
**I want** {action},
**So that** {benefit}.

**Acceptance Criteria:**
- [ ] Given {precondition}, when {action}, then {expected result}

### Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| {e.g., Invalid input submitted} | {e.g., Return 400 with descriptive error message} |
| {e.g., Resource not found} | {e.g., Return 404 with resource identifier} |
| {e.g., Concurrent modification} | {e.g., Return 409 with current version for resolution} |

## Functional Requirements

### FR-001: {Requirement Name}
**Priority:** Critical | High | Medium | Low
**Related User Stories:** {US1, US3}
**Description:** {Detailed requirement description}
**Acceptance Criteria:**
- {Specific, testable criterion}
- {Specific, testable criterion}

### FR-002: {Requirement Name}
**Priority:** Critical | High | Medium | Low
**Related User Stories:** {US2}
**Description:** {Detailed requirement description}
**Acceptance Criteria:**
- {Specific, testable criterion}

## Non-Functional Requirements

### Performance
- **Response Time:** {target, e.g., p95 < 200ms for API responses}
- **Throughput:** {target, e.g., 1000 requests/second}
- **Resource Usage:** {constraints, e.g., < 512MB RAM per instance}

### Security
- **Authentication:** {requirements, e.g., JWT-based with refresh tokens}
- **Authorization:** {requirements, e.g., role-based access control}
- **Data Protection:** {requirements, e.g., encryption at rest and in transit}

### Reliability
- **Availability:** {target, e.g., 99.9% uptime}
- **Recovery Time Objective (RTO):** {target, e.g., < 1 hour}
- **Recovery Point Objective (RPO):** {target, e.g., < 5 minutes}

## Key Entities

| Entity | Description | Key Fields |
|--------|-------------|------------|
| {Entity Name} | {What it represents in the domain} | {Important fields/attributes} |
| {Entity Name} | {What it represents in the domain} | {Important fields/attributes} |

## Clarifications

<!-- Populated by the clarify phase. Each entry has Question, Impact, and Recommendation. -->
