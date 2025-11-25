# All comments in English.
FROM python:3.10-slim
WORKDIR /app

COPY ./requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/
# ===== commands/vectorstore_cmd/Dockerfile =====
ENTRYPOINT ["python", "-m", "commands.vectorstore_cmd.build_vectorstore_multi_stage_zerohedge"]

