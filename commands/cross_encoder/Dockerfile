# File: commands/cross_encoder/Dockerfile
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04
LABEL org.opencontainers.image.title="cross_encoder_standalone"
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip gcc && rm -rf /var/lib/apt/lists/*
COPY commands/cross_encoder/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY commands/cross_encoder/cross_encoder_svc.py commands/cross_encoder/cross_encoder_svc.py
COPY logic/ logic/
CMD ["python3", "commands/cross_encoder/cross_encoder_svc.py"]
