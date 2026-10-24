ARG PYTHON_IMAGE=python:3.14-slim
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libseccomp2 && rm -rf /var/lib/apt/lists/*
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --create-home --uid 10001 projecttrace && mkdir -p /app/data && chown projecttrace:projecttrace /app/data
COPY backend backend
COPY analyzers analyzers
COPY integrations integrations
COPY workers workers
COPY scripts scripts
COPY samples samples
COPY alembic.ini .
USER projecttrace
EXPOSE 8011
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8011"]
