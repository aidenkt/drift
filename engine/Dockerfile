# The engine as a container, for any host that runs one (Render, Railway, Fly, Cloud Run).
# Build from the repo root, since the engine reads ../schema and ../data:
#   docker build -f engine/Dockerfile -t since-engine .
# Keys come from the environment (see .env.example); nothing secret is in the image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TQDM_DISABLE=1
WORKDIR /app
COPY schema schema
COPY data data
COPY engine engine
RUN pip install -e ./engine

WORKDIR /app/engine
EXPOSE 8000
# one worker: reports and loaded workbooks live in this process's memory
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
