# Pin the Python patch series and distro; do not use a floating latest tag.
FROM python:3.13.16-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements/ requirements/
RUN python -m pip install -r requirements/dev.txt
COPY pyproject.toml README.md ./
COPY src/ src/
COPY tests/ tests/
RUN python -m pip install --no-deps --no-build-isolation -e ".[dev]"

CMD ["sh", "-c", "python -m pytest && python -m ruff check . && python -m ruff format --check ."]
