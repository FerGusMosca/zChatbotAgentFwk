# All comments in English.
FROM python:3.10-slim
WORKDIR /app

COPY ./requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/
ENTRYPOINT ["python", "/app/build_vectorstore_multi_stage_zerohedge.py"]
