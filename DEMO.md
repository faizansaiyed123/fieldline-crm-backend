# Fieldline CRM backend demo API

This branch adds a standalone FastAPI simulator for the Fieldline CRM frontend. It is intentionally separate from the production app.

## Start

Python 3.13 or newer is required by the project.

    python -m pip install -e ".[dev]"
    python demo_app.py

The simulator binds only to 127.0.0.1:8001. API docs are at http://127.0.0.1:8001/docs.

## Demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Owner | alex@fieldline.demo | Demo1234! |
| Member | jordan@fieldline.demo | Demo1234! |

Use the browser-local frontend demo by default. To connect the frontend to this server, set NEXT_PUBLIC_FIELDLINE_DEMO=false and BACKEND_URL=http://127.0.0.1:8001 in the frontend .env.local file.

## Isolation and limits

The simulator stores synthetic CRM state in process memory and resets whenever the process restarts. It does not import the production FastAPI application, SQLAlchemy models, PostgreSQL driver, migrations, authentication token implementation, or production settings. It does not connect to PostgreSQL or any external service. Its auth tokens and cookies are demo-only and must never be used in production.

The API implements demo login/session refresh, organization-scoped company/contact and opportunity CRUD, pipeline stages, relationship context and graph, activities/tasks, planner and attention results, saved views, CSV import preview/dry-run/commit, data-quality merge, automation rules/runs, business-rule updates, and simulated system health.

External email, webhook delivery, payment processing, and production customer data are not used.

## Tests

    ruff check demo_app.py demo_tests
    python -m compileall -q demo_app.py demo_tests
    python -m pytest demo_tests -q

The isolated test suite uses FastAPI TestClient and the in-memory seed. It does not connect to PostgreSQL or alter the production test fixtures.
