# Architectural Decisions

## ADR-001 — Modular monolith first

**Decision:** Build the CRM as a modular monolith.

**Reason:** The product needs strong boundaries, transactional consistency, and maintainability more than it needs distributed services. Splitting too early would add operational complexity without a demonstrated workload need.

## ADR-002 — PostgreSQL as the system of record

**Decision:** Use PostgreSQL for CRM data, workflows, audit history, and search primitives.

**Reason:** The data model is relational, integrity matters, and PostgreSQL provides mature constraints, indexing, full-text search, and transactional/concurrency controls.

## ADR-003 — Backend-first

**Decision:** Stabilize the API, data model, authorization, and business rules before serious frontend integration.

**Reason:** The frontend must consume real contracts and real error semantics rather than mock behavior.

## ADR-004 — Deterministic explainability over opaque scoring

**Decision:** Attention and relationship-health features expose contributing signals.

**Reason:** Small teams need to know why the CRM is asking for attention. Transparent rules are easier to validate, test, and audit.

## ADR-005 — PostgreSQL-native search initially

**Decision:** Start with PostgreSQL indexes and full-text search.

**Reason:** It keeps the core product self-contained. External search will only be justified by measured requirements.

## ADR-006 — Security-sensitive session design

**Decision:** Treat session/token handling as a first-class subsystem.

**Reason:** OWASP guidance emphasizes secure session identifiers, lifecycle controls, TLS, cookie protections, and backend-enforced authorization. These controls must be designed in rather than added after the UI exists.

## ADR-007 — Open-source-only core

**Decision:** No paid external service is required for the core product.

**Reason:** The product should remain reproducible and usable locally and in a low-cost deployment environment.

## ADR-008 — Incremental Git history

**Decision:** Each coherent engineering unit is tested, reviewed, committed, and pushed.

**Reason:** The repository should reflect real development progression and make regressions/recovery easier to reason about.

## Research references

- HubSpot CRM overview: https://www.hubspot.com/products/crm
- Salesforce small-business CRM checklist: https://www.salesforce.com/crm/checklist/
- FastAPI security: https://fastapi.tiangolo.com/tutorial/security/
- FastAPI JWT/password hashing: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
- FastAPI testing: https://fastapi.tiangolo.com/tutorial/testing/
- PostgreSQL documentation: https://www.postgresql.org/docs/current/
- Playwright testing/accessibility: https://playwright.dev/docs/accessibility-testing
- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
