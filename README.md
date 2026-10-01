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

## One-command local startup

After the backend dependencies and frontend dependencies are installed, `run.py` starts the complete local development stack:

```bash
python run.py
```

The launcher reuses the existing PostgreSQL Compose service, waits for PostgreSQL readiness, applies Alembic migrations, starts the existing FastAPI application with Uvicorn, and starts the companion Next.js development server.

Because the frontend and backend are separate repositories, `run.py` discovers a nearby checkout of `fieldline-crm-frontend` when possible. For a frontend checkout elsewhere, set `FIELDLINE_FRONTEND_DIR` or pass its path explicitly:

```bash
python run.py --frontend-dir /path/to/fieldline-crm-frontend
```

The launcher never starts a second backend or frontend when the expected endpoint is already healthy.

### Local ports

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000`
- API documentation: `http://127.0.0.1:8000/api/v1/docs`

## Docker startup

The backend repository can be run independently with Docker Compose:

```bash
docker compose up --build
```

This starts:

- PostgreSQL 18 on host port `5432`
- The FastAPI backend on host port `8000`

The API container waits for PostgreSQL health, applies all pending Alembic migrations, and then starts Uvicorn. The container readiness endpoint is `/api/v1/ready`.

Stop the stack:

```bash
docker compose down
```

Rebuild the stack:

```bash
docker compose up --build
```

The PostgreSQL data volume is preserved by `docker compose down`. Use `docker compose down -v` only when you intentionally want to remove the local database data.

## Environment variables

Development defaults are already defined by the application and Docker Compose. Create a local `.env` when you need to override them.

| Variable | Purpose |
| --- | --- |
| `FIELDLINE_ENVIRONMENT` | Runtime environment name; use `development` locally. |
| `FIELDLINE_DEBUG` | FastAPI debug flag. |
| `FIELDLINE_DATABASE_URL` | SQLAlchemy PostgreSQL connection URL. Docker Compose uses the `postgres` service hostname by default. |
| `FIELDLINE_API_PREFIX` | API route prefix; defaults to `/api/v1`. |
| `FIELDLINE_JWT_SECRET_KEY` | JWT signing secret; use a strong, private value outside local development. |
| `FIELDLINE_JWT_ALGORITHM` | JWT signing algorithm. |
| `FIELDLINE_JWT_ISSUER` | JWT issuer claim. |
| `FIELDLINE_JWT_AUDIENCE` | JWT audience claim. |
| `FIELDLINE_ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime. |
| `FIELDLINE_REFRESH_TOKEN_EXPIRE_DAYS` | Refresh-session lifetime. |
| `FIELDLINE_SECURE_COOKIES` | Enables production Secure cookie validation. |

Do not commit `.env` or production credentials.

## Database

PostgreSQL is the system of record. The repository already contains an Alembic migration chain through `0012_standout`. The Dockerized backend applies pending migrations automatically before starting the API.

For manual local setup, run:

```bash
python -m alembic upgrade head
```

The final migration also enables the PostgreSQL `pg_trgm` extension used by the data-quality duplicate detection path.

## Redis

Redis is not used by the current backend. No Redis container, worker, queue, or scheduler is required.

## Tests

```bash
ruff check app tests
python -m pytest
```

The integration suite expects PostgreSQL.

## Frontend

The companion web application lives in [fieldline-crm-frontend](https://github.com/faizansaiyed123/fieldline-crm-frontend).

The frontend uses a same-origin Next.js API rewrite and points that rewrite to this backend with `BACKEND_URL`.
