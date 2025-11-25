# All comments in English.
FROM python:3.10-slim
WORKDIR /app

# Install system deps for FAISS
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy ONLY this module’s requirements
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy full folder
COPY . /app/

# Default entrypoint
ENTRYPOINT ["python", "/app/build_vectorstore_multi_stage_zerohedge.py"]
