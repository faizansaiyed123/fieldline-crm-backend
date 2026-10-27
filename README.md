# Fieldline CRM Backend

Backend API for Fieldline CRM, a small-business CRM for customer records, sales pipeline workflows, follow-up activities, data quality, and operational workflows.

Explore the [Fieldline CRM product walkthrough](https://github.com/faizansaiyed123/fieldline-crm-frontend/blob/main/docs/PRODUCT-WALKTHROUGH.md) and [feature coverage matrix](https://github.com/faizansaiyed123/fieldline-crm-frontend/blob/main/docs/FEATURE-COVERAGE.md) in the companion frontend repository.

## Key features

- **CRM records:** Organization-scoped company and contact management, pipeline stages, opportunities, tasks, activities, search, and record archiving.
- **Imports and saved views:** Contact CSV preview and validation, dry runs, import commits, and reusable contact views with visibility controls.
- **Operational intelligence:** Attention queue, relationship health, relationship graph, duplicate detection, controlled contact and company merges, work planner, and stuck-opportunity reporting.
- **Automation:** Configurable opportunity-triggered rules, execution history, and organization-specific business rules.
- **Authentication and authorization:** Password hashing with Argon2, JWT access tokens, server-side refresh sessions with rotation, CSRF validation, organization membership and role checks, and database-backed authentication throttling.
- **Auditing and diagnostics:** Audit events, health and readiness endpoints, and system-health checks.

## Stack and architecture

- Python 3.13+
- FastAPI and Uvicorn
- PostgreSQL 18 and SQLAlchemy 2
- Alembic database migrations
- Pydantic and Pydantic Settings
- PyJWT and Argon2
- pytest, HTTPX, pytest-cov, and Ruff

The application is organized as a single FastAPI service with separate API, authentication, schema, model, and service modules. PostgreSQL stores application data, and Alembic manages database schema changes. Organization membership and role dependencies are used to control access to organization-scoped resources.

Authentication uses signed access tokens and persisted refresh sessions. Refresh tokens are stored as hashes, and session refresh uses CSRF validation. Authentication throttling is also stored in PostgreSQL.

See the [architecture documentation](docs/ARCHITECTURE.md) for the documented system design.

## Companion frontend

The web application lives in [fieldline-crm-frontend](https://github.com/faizansaiyed123/fieldline-crm-frontend).

The frontend uses a same-origin Next.js API rewrite and configures its backend destination through `BACKEND_URL`.

## Quick start

### Docker Compose

Start PostgreSQL and the backend:

```bash
docker compose up --build
```

The stack exposes PostgreSQL on port `5432` and the API on port `8000`. The API container applies pending Alembic migrations before starting Uvicorn.

Stop the stack:

```bash
docker compose down
```

The PostgreSQL volume is preserved by `docker compose down`. Use `docker compose down -v` only when you intentionally want to remove the local database data.

The Compose file includes development fallback configuration. Do not use development credentials or signing secrets for a public production deployment.

### Local Python setup

Start PostgreSQL:

```bash
docker compose up -d
```

Create and activate a virtual environment, then install the development dependencies:

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
```

Create a local `.env` from `.env.example`, then apply migrations:

```bash
python -m alembic upgrade head
```

Start the API:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

The API uses the `/api/v1` prefix by default. Interactive API documentation is available at `/api/v1/docs`, and the readiness endpoint is `/api/v1/ready`.

### One-command backend startup

After installing the backend dependencies and configuring the environment, run:

```bash
python run.py
```

The launcher loads the local `.env` file when available, starts the Compose PostgreSQL service if local PostgreSQL is needed and not already running, applies pending migrations, and starts the FastAPI application. It monitors the backend process until shutdown.

## Environment variables

The following names come from `.env.example`, `docker-compose.yml`, and `Dockerfile`. Configure the values in your local environment or deployment settings as appropriate.

- `FIELDLINE_ENVIRONMENT`
- `FIELDLINE_DEBUG`
- `FIELDLINE_DATABASE_URL`
- `FIELDLINE_API_PREFIX`
- `FIELDLINE_JWT_SECRET_KEY`
- `FIELDLINE_JWT_ALGORITHM`
- `FIELDLINE_JWT_ISSUER`
- `FIELDLINE_JWT_AUDIENCE`
- `FIELDLINE_ACCESS_TOKEN_EXPIRE_MINUTES`
- `FIELDLINE_REFRESH_TOKEN_EXPIRE_DAYS`
- `FIELDLINE_SECURE_COOKIES`
- `FIELDLINE_DOCKER_DATABASE_URL`
- `FORWARDED_ALLOW_IPS`

For production, use a private or access-restricted database, a unique JWT signing secret, and secure cookies. When deploying behind a reverse proxy, configure forwarded-header trust for the actual trusted proxy addresses. Keep `.env` files and production credentials out of Git.

## Database

The repository contains an Alembic migration chain through `0012_standout`. The migrations create the CRM schema, identity and session tables, activity and audit records, automation, imports, saved views, and supporting operational tables.

The final migration enables PostgreSQL's `pg_trgm` extension, which the data-quality duplicate-detection functionality uses.

## Redis

Redis is not used by the current backend. The repository does not require a Redis container, worker, queue, or scheduler for its current implementation.

## Tests

Install the development dependencies before running the checks.

Run linting:

```bash
ruff check app tests
```

Run Python compilation checks:

```bash
python -m compileall -q app tests migrations
```

Apply database migrations when a configured database is available:

```bash
python -m alembic upgrade head
```

Run the test suite:

```bash
python -m pytest
```

Build the Docker image:

```bash
docker build --tag fieldline-crm-backend:local .
```

The integration tests expect PostgreSQL. The backend CI workflow runs linting, compilation, database migrations, pytest with coverage reporting, and a Docker image build.

## Project structure

```text
fieldline-crm-backend/
├── app/
│   ├── api/          # FastAPI route modules
│   ├── auth/         # Authentication, sessions and authorization
│   ├── core/         # Application settings and HTTP handling
│   ├── db/           # Database infrastructure
│   ├── models/       # SQLAlchemy models
│   ├── schemas/      # Request and response schemas
│   └── services/     # CRM and workflow logic
├── migrations/
│   └── versions/     # Alembic migration revisions
├── tests/            # API, model, auth and workflow tests
├── docs/             # Architecture and project documentation
├── .github/
│   └── workflows/    # Backend CI
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── pyproject.toml
└── run.py             # Local backend launcher
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Architectural decisions](docs/DECISIONS.md)
- [Changelog](docs/CHANGELOG.md)
- [Project status](docs/PROJECT_STATUS.md)
- [Roadmap](docs/ROADMAP.md)

The companion frontend repository provides the [product walkthrough](https://github.com/faizansaiyed123/fieldline-crm-frontend/blob/main/docs/PRODUCT-WALKTHROUGH.md) and [feature coverage matrix](https://github.com/faizansaiyed123/fieldline-crm-frontend/blob/main/docs/FEATURE-COVERAGE.md).
