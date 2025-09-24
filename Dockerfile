# Imagen base con Python
FROM python:3.11-slim

# Set working dir
WORKDIR /app

# Copiar requirements y instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Exponer el puerto (lo tenés en .env como 8000)
EXPOSE 8000

# Comando de arranque (ajustá si usás FastAPI/Flask)
CMD ["python", "main.py"]
