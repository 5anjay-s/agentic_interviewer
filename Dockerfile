# Stage 1 - frontend build
FROM node:18 AS node_builder
WORKDIR /workspace/frontend
COPY frontend/package*.json frontend/
COPY frontend/ ./
RUN npm ci
RUN npm run build

# Stage 2 - python backend
FROM python:3.12-slim
WORKDIR /app
# System deps for audio processing (if used)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . /app

# Copy frontend build into /app/static to be served by FastAPI static mount
COPY --from=node_builder /workspace/frontend/dist ./static

ENV PYTHONUNBUFFERED=1
ENV PARSER_BUCKET=""
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
