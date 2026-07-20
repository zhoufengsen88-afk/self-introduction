FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app/apps/api/src:/lite-llmops-sdk"

WORKDIR /app

RUN pip install --no-cache-dir \
    "alembic>=1.17.2" \
    "fastapi>=0.122.1" \
    "httpx>=0.28.1" \
    "markdown-it-py>=4.0.0" \
    "psycopg[binary]>=3.3.2" \
    "pydantic-settings>=2.12.0" \
    "python-frontmatter>=1.1.0" \
    "sqlalchemy>=2.0.44" \
    "uvicorn[standard]>=0.38.0"

COPY alembic.ini ./
COPY apps/api ./apps/api
COPY knowledge ./knowledge

EXPOSE 8000

CMD ["uvicorn", "self_intro_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
