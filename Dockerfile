FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy
WORKDIR /app
RUN apt-get update && apt-get install -y libpoppler-cpp-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
COPY . .
ENV PORT=8000
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]