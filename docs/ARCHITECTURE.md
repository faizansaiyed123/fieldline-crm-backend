# Architecture

## Product architecture

Fieldline is a modular monolith first. The domain boundaries should be strong enough to evolve independently without prematurely distributing the application into services.

```
Browser
  │
  ▼
Next.js App Router
  │ HTTPS / JSON
  ▼
FastAPI
  ├── authentication / authorization
  ├── API schemas
  ├── CRM domain services
  ├── workflow evaluation
  ├── import pipeline orchestration
  ├── audit recording
  └── observability
        │
        ▼
   SQLAlchemy 2
        │
        ▼
   PostgreSQL
```

## Backend layering

Each domain should separate:

- API route handling and HTTP concerns
- input/output validation
- business rules
- database access
- authorization
- side-effect orchestration
- audit/event recording

The codebase should prefer functions and small modules over class-heavy abstractions.

## Database principles

PostgreSQL is the system of record. Foreign keys and unique constraints enforce invariants that should not depend only on application checks. Indexes should reflect real access patterns, including ownership/status/date filters and search paths. Transactions protect multi-step workflows such as merges, imports, and automation side effects.

PostgreSQL 18 is the current documented stable series as of this project's research date; the implementation should pin a tested major version through local/container configuration rather than depending on a floating production database version.

## Search

Start with PostgreSQL-native search for CRM fields and notes. Full-text search can use `tsvector` plus a GIN index where profiling confirms the workload benefits from it. Add external search infrastructure only if real requirements make it necessary.

## Authentication

The application will use password hashing with Argon2, short-lived signed access tokens, and a server-controlled session lifecycle. Sensitive session material should never be logged. Browser-facing cookies must use appropriate Secure, HttpOnly, and SameSite properties when cookies are used.

## Authorization

Authorization is deny-by-default and enforced in backend code for every protected resource. Organization/tenant scope is part of authorization, not merely a frontend filter.

## Attention signals

Attention scoring is deterministic and explainable. A result should be represented as concrete reasons such as overdue follow-up, no activity for N days, or opportunity stuck in a stage. These rules are not branded as AI.

## Import pipeline

```
upload
  → parse
  → schema validation
  → duplicate checks
  → preview
  → problem resolution
  → transaction-safe import
  → summary + audit
```

Large imports should be processed in bounded work units so the API request does not become an unbounded transaction or memory sink.

## Testing strategy

- unit tests for deterministic domain rules
- API tests with FastAPI/HTTPX
- database integration tests against PostgreSQL
- authorization/security tests
- workflow tests
- frontend tests
- Playwright end-to-end tests
- automated accessibility checks plus manual review

## CI

CI will run formatting/linting, backend tests, frontend checks, and end-to-end tests once each layer exists. CI should fail closed on test or build failures and should not require paid services.
