# Runtime image for the API. PostgreSQL runs in its own container,
# see docker-compose.yml.

FROM python:3.12-slim

# PYTHONDONTWRITEBYTECODE keeps .pyc files out of the image.
# PYTHONUNBUFFERED makes logs appear immediately instead of being held in a
# buffer, which matters when `docker compose logs` is how you debug.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

# Dependencies are copied and installed before the application code so that
# editing a source file doesn't invalidate the cached pip layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests
COPY pytest.ini .

# Run as an unprivileged user rather than root. /code is handed over too, so
# that pytest can write its cache when the suite is run inside the container.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /code
USER appuser

EXPOSE 8000

# No --reload here. That is a development convenience and it doubles the
# process count.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
