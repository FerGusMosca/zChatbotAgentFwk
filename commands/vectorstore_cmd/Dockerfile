# ===== commands/vectorstore_cmd/Dockerfile =====
# All comments in English.

FROM python:3.10-slim
WORKDIR /app

# install deps
COPY commands/vectorstore_cmd/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy WHOLE framework (critical)
COPY . /app/

# run module, never a .py file
ENTRYPOINT ["python", "-m", "commands.vectorstore_cmd.build_vectorstore_multi_stage_zerohedge"]
