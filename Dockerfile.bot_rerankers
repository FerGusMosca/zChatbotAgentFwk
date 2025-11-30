FROM python:3.10-slim

WORKDIR /app

# Copiamos TODO
COPY . /app

# 1. Instalamos las dependencias comunes (sin sentence-transformers)
RUN pip install --no-cache-dir -r requirements.txt

# 2. Instalamos SOLO las pesadas del bot10
COPY requirements_bot_rerankers.txt .
RUN pip install --no-cache-dir -r requirements_bot_rerankers.txt

# Puerto FastAPI
EXPOSE 8080

# Arranca
CMD ["python", "main.py"]