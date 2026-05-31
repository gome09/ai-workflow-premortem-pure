# Dockerfile
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_PROJECT_ENVIRONMENT=/opt/aiwf-venv \
    PATH="/opt/aiwf-venv/bin:${PATH}"

WORKDIR /app

# Install uv first so dependency installation can be cached.
RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./

# Install the application dependency set from the checked-in lockfile.
# The project itself is not installed; source is copied below for local alpha usage.
RUN uv sync --frozen --no-install-project --extra dev

COPY . .

EXPOSE 8000 8501

CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
