# Data Model: {feature_name}

**Based on:** SPEC-{NNN} and plan.md
**Created:** {date}

## Entity Relationship Overview

```text
{Text-based entity relationship diagram}

+-------------+       +-------------+       +-------------+
|  {Entity1}  |------<|  {Entity2}  |>------|  {Entity3}  |
+-------------+       +-------------+       +-------------+
```

## Entities

### {Entity Name}

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | {UUID / Integer} | PK, NOT NULL | Unique identifier |
| {field_name} | {type} | {NOT NULL, UNIQUE, etc.} | {Description} |
| {field_name} | {type} | {constraints} | {Description} |
| created_at | DateTime | NOT NULL, DEFAULT NOW() | Creation timestamp |
| updated_at | DateTime | NOT NULL, DEFAULT NOW() | Last update timestamp |

**Indexes:**
- {index_name} on ({fields}) — {purpose}

**Relationships:**
- **belongs_to** {OtherEntity} via {foreign_key_field}
- **has_many** {OtherEntity} via {child_foreign_key_field}

**Validation Rules:**
- {field_name}: {validation rule, e.g., must be valid email format}
- {field_name}: {validation rule, e.g., must be > 0}

### {Entity Name}

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | {type} | PK, NOT NULL | Unique identifier |
| {field_name} | {type} | {constraints} | {Description} |
| created_at | DateTime | NOT NULL, DEFAULT NOW() | Creation timestamp |
| updated_at | DateTime | NOT NULL, DEFAULT NOW() | Last update timestamp |

**Indexes:**
- {index_name} on ({fields}) — {purpose}

**Relationships:**
- **belongs_to** {OtherEntity} via {foreign_key_field}

**Validation Rules:**
- {field_name}: {validation rule}

## Enumerations

### {Enum Name}

| Value | Description |
|-------|-------------|
| {VALUE_1} | {What this value represents} |
| {VALUE_2} | {What this value represents} |
| {VALUE_3} | {What this value represents} |

## Migration Notes

- **Initial migration:** Creates tables for {entities}
- **Data seeding:** {Seed data requirements, if any}
- **Rollback plan:** {How to safely roll back schema changes}
