# --- Base Stage ---
# Common base for both Python app and JS tests
FROM python:3.12-slim as base
WORKDIR /app
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# --- Node.js Test Stage ---
# This stage is only for running JS tests
FROM node:20-slim as node-test
WORKDIR /app
COPY package.json ./
RUN npm install
COPY tests/js/ ./tests/js/
COPY static/main.js ./static/main.js
RUN npm test

# --- Final Python App Stage ---
# This is the final image for the API server
FROM base as final
WORKDIR /app

# Install uv using the official installer
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Copy only dependency files first to leverage Docker cache
COPY uv.lock pyproject.toml ./
# Install Python dependencies
RUN uv sync --locked

# Copy the rest of the application code
COPY ./src /app/src
COPY ./models /app/models
COPY ./static /app/static

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/src"]
