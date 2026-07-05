# Tasks: {feature_name}

**Based on:** plan.md for SPEC-{NNN}
**Created:** {date}

## Dependency Graph

```text
Phase 1: Setup (T001-T00X)
  |
Phase 2: Foundational (T00X-T00X)
  |
  +-- Phase 3: US1 - {title} (T00X-T00X) [P]
  +-- Phase 4: US2 - {title} (T00X-T00X) [P]
  +-- Phase 5: US3 - {title} (T00X-T00X) [P]
  |
Phase 6: Integration (T00X-T00X)
  |
Phase 7: Polish & Release (T00X-T00X)
```

**Legend:**
- `[P]` = Parallelizable (no dependencies on other tasks in same phase)
- `[Story]` = Associated user story (US1, US2, US3)
- `Deps:` = Must complete listed tasks first

---

## Phase 1: Setup

- [ ] T001 Create project directory structure as defined in plan.md
- [ ] T002 [P] Initialize package manager and install dependencies
- [ ] T003 [P] Configure environment variables and .env.example
- [ ] T004 [P] Set up linting and formatting configuration
- [ ] T005 Initialize version control (git init, .gitignore)

## Phase 2: Foundational

- [ ] T006 Create database schema and run initial migration
- [ ] T007 [P] Implement base model/entity classes
- [ ] T008 [P] Implement error handling framework
- [ ] T009 [P] Configure logging infrastructure
- [ ] T010 [P] Set up authentication/authorization middleware

## Phase 3: User Story 1 - {title} (Priority: P1)

- [ ] T011 [P] [US1] Create {Model} in {file_path} (Deps: T006, T007)
- [ ] T012 [P] [US1] Create {Repository/DAO} in {file_path} (Deps: T006, T011)
- [ ] T013 [US1] Implement {Service} in {file_path} (Deps: T011, T012)
- [ ] T014 [US1] Create {API Endpoint} in {file_path} (Deps: T013)
- [ ] T015 [P] [US1] Write unit tests for {feature} in {test_file} (Deps: T013, T014)
- [ ] T016 [P] [US1] Write integration tests for {feature} in {test_file} (Deps: T014)

**Checkpoint:** All US1 acceptance criteria pass. Manual smoke test succeeds.

## Phase 4: User Story 2 - {title} (Priority: P2)

- [ ] T017 [P] [US2] Create {Model} in {file_path} (Deps: T006, T007)
- [ ] T018 [P] [US2] Create {Repository/DAO} in {file_path} (Deps: T006, T017)
- [ ] T019 [US2] Implement {Service} in {file_path} (Deps: T017, T018)
- [ ] T020 [US2] Create {API Endpoint} in {file_path} (Deps: T019)
- [ ] T021 [P] [US2] Write tests for {feature} in {test_file} (Deps: T019, T020)

**Checkpoint:** All US2 acceptance criteria pass. US1 continues to pass.

## Phase 5: User Story 3 - {title} (Priority: P3)

- [ ] T022 [P] [US3] Create {Model} in {file_path} (Deps: T006, T007)
- [ ] T023 [US3] Implement {Service} in {file_path} (Deps: T022)
- [ ] T024 [US3] Create {API Endpoint} in {file_path} (Deps: T023)
- [ ] T025 [P] [US3] Write tests for {feature} in {test_file} (Deps: T023, T024)

**Checkpoint:** All US3 acceptance criteria pass. US1 and US2 continue to pass.

## Phase 6: Integration

- [ ] T026 Cross-cutting integration tests (Deps: T016, T021, T025)
- [ ] T027 [P] API documentation generation (Deps: T014, T020, T024)
- [ ] T028 [P] Performance baseline and load testing (Deps: T026)

## Phase 7: Polish & Release

- [ ] T029 [P] Input validation audit across all endpoints
- [ ] T030 [P] Error message consistency review
- [ ] T031 [P] Security audit (OWASP top 10 checklist)
- [ ] T032 Final review against spec.md acceptance criteria
- [ ] T033 Update README and quickstart guide
