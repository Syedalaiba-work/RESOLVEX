FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/ backend/
COPY tests/ tests/
COPY pytest.ini .coveragerc ./

RUN useradd --create-home appuser && chown -R appuser /srv
USER appuser

ENV PYTHONPATH=/srv/backend
EXPOSE 8080
# One process keeps the in-memory rate limiter exact; the database does the concurrency control.
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
