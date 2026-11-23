FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never PYTHONPATH=/app/src PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
EXPOSE 6027
CMD ["python", "-m", "uvicorn", "auto_ocr.webhook:app", "--host", "0.0.0.0", "--port", "6027"]
