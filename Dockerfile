FROM python:3.10-slim

WORKDIR /app

# Copy only the app code
COPY . /app

RUN apt-get update && apt-get install -y \
    unixodbc \
    unixodbc-dev \
    libpq-dev \
    g++ \
    && rm -rf /var/lib/apt/lists/*


# Install deps
RUN pip install --no-cache-dir -r requirements.txt

# Expose port if needed (FastAPI?)
EXPOSE 8080

# Default command
CMD ["python", "main.py"]
