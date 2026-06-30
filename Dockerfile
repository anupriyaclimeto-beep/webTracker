# Stage 1: Build the React frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./

ARG VITE_AUTH_API_BASE_URL
ARG VITE_PORTAL_URL
ENV VITE_AUTH_API_BASE_URL=$VITE_AUTH_API_BASE_URL
ENV VITE_PORTAL_URL=$VITE_PORTAL_URL

RUN npm run build

# Stage 2: Build the Python backend
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies (needed for psycopg2 and others)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements (UTF-8; avoid Windows UTF-16 requirements.txt)
COPY requirements-docker.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Install Playwright and its system dependencies (only Chromium to save space)
RUN playwright install --with-deps chromium

# Copy all backend code
COPY . .

# Copy built React frontend files from Stage 1
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Expose port (Railway sets PORT environment variable, defaults to 5000)
ENV PORT=5000
EXPOSE $PORT

# Start Gunicorn server (api.py is our Flask app)
CMD gunicorn --bind 0.0.0.0:$PORT api:app
