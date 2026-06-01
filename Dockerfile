# ==========================================
# Stage 1: Build the Vite Frontend
# ==========================================

FROM node:20-alpine AS frontend-builder

WORKDIR /app

# Copy package files and install frontend dependencies
COPY package*.json ./
RUN npm ci

# Copy the frontend configuration and source code
COPY vite.config.js index.html ./
COPY src/ ./src/

# Build the static assets (outputs to /app/dist by default)
RUN npm run build

# ==========================================
# Stage 2: Build the Flask Backend & Final Image
# ==========================================
FROM python:3.11-slim AS backend-runner
WORKDIR /app

# Prevent Python from writing .pyc files and enable buffering
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn

# Copy backend files and application data
COPY app.py ./
COPY template_spreadsheet.csv ./

# Copy the compiled static frontend assets from Stage 1 into the 'static' folder
COPY --from=frontend-builder /app/dist/ /app/static/

# Azure App Service expects containers to listen on port 8080 by default
EXPOSE 8080

# Run the application using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]