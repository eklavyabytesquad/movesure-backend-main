FROM python:3.12-slim

WORKDIR /app

# Ensure Python output is sent straight to stdout (visible immediately in Coolify logs)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system deps required by some Python packages (e.g. Pillow, barcode)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libzbar0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (maximises layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Non-root user for security
RUN useradd -r appuser && chown -R appuser /app
USER appuser

EXPOSE 5000

# Gunicorn + Uvicorn workers — 2 workers, 120 s timeout
CMD ["gunicorn", "main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "2", \
     "--bind", "0.0.0.0:5000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info", \
     "--capture-output"]
