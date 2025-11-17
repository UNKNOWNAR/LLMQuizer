# 1. Use the official Playwright image (This is the most critical fix)
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# 2. Set working directory
WORKDIR /app

# 3. Install system-level dependencies for our tools
# This is critical for PDF and other libraries
RUN apt-get update && apt-get install -y \
    libpoppler-cpp-dev \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# 4. Copy and install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Note: `playwright install` is NOT needed, as the base image already has browsers.

# 5. Copy the application code (Note: COPY . . copies everything)
COPY . .

# 6. Cloud Run listens on $PORT, default 8080
# Uvicorn will automatically use $PORT if available.
ENV PORT=8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]