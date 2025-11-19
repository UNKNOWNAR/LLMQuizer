# Production Dockerfile for Railway
FROM python:3.10-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# System dependencies for potential OCR/PDF features
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY main.py /app/main.py

# Expose port and run
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]