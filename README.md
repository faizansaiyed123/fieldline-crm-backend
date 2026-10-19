# Fieldline CRM Backend

Backend API for **Fieldline CRM**, a production-minded small-business CRM focused on customer context, pipeline execution, data integrity, and explainable operational intelligence.

## Stack

- Python 3.13+
- FastAPI
- SQLAlchemy 2
- PostgreSQL 18
- Alembic
- JWT access tokens + rotated refresh-token sessions
- Argon2 password hashing
- pytest / HTTPX
- Ruff

## Local setup

Start PostgreSQL:

```bash
docker compose up -d
```

Install the backend:

```bash
python -m venv .venv
# activate the virtual environment
python -m pip install -e ".[dev]"
```

Create `.env` from `.env.example`, then run migrations:

```bash
python -m alembic upgrade head
```

Start the API:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

The API is available at `/api/v1`. Interactive documentation is available at `/api/v1/docs`.

## One-command backend startup

After the backend dependencies are installed, run:

```bash
python run.py
```

The launcher is backend-only. It:

1. Loads the backend `.env` values.
2. Starts the existing PostgreSQL Compose service when the configured database points to local PostgreSQL on port 5432.
3. Waits for PostgreSQL to become ready.
4. Applies all pending Alembic migrations.
5. Starts the existing FastAPI application with Uvicorn on port 8000.
6. Waits for the API to respond before handing control back to the terminal.
7. Keeps monitoring the backend process until you stop it with Ctrl+C.

The frontend is intentionally not started or discovered by `run.py`. The frontend lives in its own repository and can be run independently there.

### Local backend ports

- PostgreSQL: `localhost:5432`
- Backend: `http://127.0.0.1:8000`
- API documentation: `http://127.0.0.1:8000/api/v1/docs`

## Docker startup

The backend repository can be run independently with Docker Compose:

```bash
docker compose up --build
```

This local development stack starts PostgreSQL 18 on host port `5432` and the FastAPI backend on host port `8000`. The API container applies pending Alembic migrations before starting Uvicorn. The container readiness endpoint is `/api/v1/ready`.

Stop the stack:

```bash
docker compose down
```

Rebuild the stack:

```bash
docker compose up --build
```

The PostgreSQL data volume is preserved by `docker compose down`. Use `docker compose down -v` only when you intentionally want to remove the local database data.

**Do not use the Compose fallback credentials for a public production deployment.** For production, use a managed/private PostgreSQL instance or otherwise restrict database network access; provide production secrets and settings explicitly.

## Production configuration

Set these environment variables in the deployment platform's secret/configuration settings:

```env
FIELDLINE_ENVIRONMENT=production
FIELDLINE_DEBUG=false
FIELDLINE_DATABASE_URL=postgresql+psycopg://<user>:<password>@<private-host>:5432/<database>
FIELDLINE_JWT_SECRET_KEY=<unique-random-secret-at-least-32-bytes>
FIELDLINE_SECURE_COOKIES=true
```

Use a unique JWT secret of at least 32 bytes. Keep database credentials and signing secrets out of Git. When the service is behind a reverse proxy, set `FORWARDED_ALLOW_IPS` to the trusted proxy IP addresses/CIDRs so Uvicorn accepts forwarded headers only from those proxies. It defaults to `127.0.0.1`; do not set it to `*` on an internet-facing deployment.

## Environment variables

Development defaults are available locally. Override them through your environment or a local, untracked `.env` file.

| Variable | Purpose |
| --- | --- |
| `FIELDLINE_ENVIRONMENT` | Runtime environment name; use `development` locally and `production` for production. |
| `FIELDLINE_DEBUG` | FastAPI debug flag; keep `false` in production. |
| `FIELDLINE_DATABASE_URL` | SQLAlchemy PostgreSQL connection URL for local/non-Docker runs and external production databases. |
| `FIELDLINE_DOCKER_DATABASE_URL` | Optional Docker-only database URL override. Defaults to the Compose `postgres` service so an existing local `.env` with `localhost` does not break the API container. |
| `FIELDLINE_API_PREFIX` | API route prefix; defaults to `/api/v1`. |
| `FIELDLINE_JWT_SECRET_KEY` | JWT signing secret; use a unique private value outside local development. |
| `FIELDLINE_JWT_ALGORITHM` | JWT signing algorithm. |
| `FIELDLINE_JWT_ISSUER` | JWT issuer claim. |
| `FIELDLINE_JWT_AUDIENCE` | JWT audience claim. |
| `FIELDLINE_ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime. |
| `FIELDLINE_REFRESH_TOKEN_EXPIRE_DAYS` | Refresh-session lifetime. |
| `FIELDLINE_SECURE_COOKIES` | Must be `true` in production so authentication cookies are secure. |
| `FORWARDED_ALLOW_IPS` | Comma-separated trusted reverse-proxy IPs/CIDRs for Uvicorn forwarded headers; defaults to loopback. Do not use `*` on a public service. |

Do not commit `.env` files or production credentials.

## Database

PostgreSQL is the system of record. The repository contains an Alembic migration chain through `0012_standout`. The Dockerized backend applies pending migrations automatically before starting the API.

For manual local setup, run:

```bash
python -m alembic upgrade head
```

The migrations enable the PostgreSQL `pg_trgm` extension used by the data-quality duplicate detection path.

## Redis

Redis is not used by the current backend. No Redis container, worker, queue, or scheduler is required.

## Tests

```bash
ruff check app tests
python -m pytest
docker build --tag fieldline-crm-backend:local .
```

The integration suite expects PostgreSQL. Backend CI runs linting, compile checks, migrations, the test suite, and a Docker image build.

## Frontend

The companion web application lives in [fieldline-crm-frontend](https://github.com/faizansaiyed123/fieldline-crm-frontend).

The frontend uses a same-origin Next.js API rewrite and points that rewrite to this backend with `BACKEND_URL`.
