FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    git

COPY uv.lock .
COPY pyproject.toml .
RUN pip install uv
RUN uv sync

COPY ./src /app/src
COPY ./models /app/models
COPY ./static /app/static

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
