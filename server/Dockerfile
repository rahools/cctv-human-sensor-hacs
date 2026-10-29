FROM rust:1.88-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends git python3 python3-dev build-essential pkg-config && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.6.5 /uv /usr/local/bin/uv
WORKDIR /build
RUN git clone https://github.com/undrgrnd-labs/hunch.git hunch && cd hunch && git checkout 22cf73010b0d399894068b1b9d21c5e4101514b6
RUN uv build --wheel --python /usr/bin/python3 --out-dir /wheels /build/hunch/eg2cpu && uv build --wheel --python /usr/bin/python3 --out-dir /wheels /build/hunch/hunch
RUN uv venv /opt/venv --python /usr/bin/python3 && uv pip install --python /opt/venv/bin/python /wheels/*.whl
COPY server/pyproject.toml server/download_model.py /app/
COPY server/src /app/src
RUN uv pip install --python /opt/venv/bin/python /app

FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*
ENV PATH="/opt/venv/bin:$PATH" HF_HOME="/models" HUNCH_STATE_DIR="/data" PYTHONUNBUFFERED=1
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app
WORKDIR /app
VOLUME ["/models", "/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s --start-period=2m CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz')"
ENTRYPOINT ["python"]
CMD ["-m", "uvicorn", "hunch_cctv.main:app", "--host", "0.0.0.0", "--port", "8765"]
