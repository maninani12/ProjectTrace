FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --create-home --uid 10001 projecttrace
COPY backend backend
COPY analyzers analyzers
COPY integrations integrations
COPY workers workers
COPY samples samples
COPY alembic.ini .
USER projecttrace
EXPOSE 8011
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8011"]
