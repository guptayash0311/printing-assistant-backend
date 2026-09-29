# Print shop API

FastAPI backend for the multi-tenant print shop. Version 1 stores files on a local directory, takes payment at the counter, and has two roles: `SUPER_ADMIN` and `TENANT_ADMIN`.

## Local API

Uses a virtual environment and a local SQLite file. No Docker. With `INLINE_FILE_PROCESSING=true`, PDF page counting runs inside the API, so Redis and the worker are not required.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Default platform login from `.env.example`: `admin@example.com` / `change-me-please`. Change those values before any shared deployment.

## Tests

```bash
pytest
ruff check .
```
