FROM python:3.13.16-slim-trixie@sha256:3dd7cc108ec1493442514f5c2a871af6af0ec31d768ff6e378a93340c3b3db5f AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 PATH="/app/.venv/bin:${PATH}" \
    BXVZM_LIBRARY=data/container-library
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends mpv=0.40.0-3+deb13u1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements/runtime.txt requirements/build.txt requirements/
COPY pyproject.toml README.md install.py run.py ./
COPY src/ src/
RUN python install.py
CMD ["bxvzm", "--config", "data/container-config.json", "--serve"]
