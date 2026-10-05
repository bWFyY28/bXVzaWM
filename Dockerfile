# Pin the Python patch, distro, and the image verified by Docker checks.
FROM python:3.13.16-slim-trixie@sha256:3dd7cc108ec1493442514f5c2a871af6af0ec31d768ff6e378a93340c3b3db5f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app
COPY requirements/ requirements/
COPY pyproject.toml README.md install.py run.py ./
COPY src/ src/
RUN python install.py --dev
COPY tests/ tests/

CMD ["sh", "-c", "python -m pytest && python -m ruff check . && python -m ruff format --check ."]
