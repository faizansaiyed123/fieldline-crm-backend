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

## Tests

```bash
ruff check app tests
python -m pytest
```

The integration suite expects PostgreSQL.

## Frontend

The companion web application lives in [fieldline-crm-frontend](https://github.com/faizansaiyed123/fieldline-crm-frontend).

The frontend uses a same-origin Next.js API rewrite and points that rewrite to this backend with `BACKEND_URL`.
