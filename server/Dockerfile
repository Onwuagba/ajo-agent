FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ajo ./ajo
ENV AJO_DB=/data/ajo.db PYTHONUNBUFFERED=1
RUN mkdir -p /data
EXPOSE 8100
CMD ["sh", "-c", "uvicorn ajo.api:app_factory --factory --host 0.0.0.0 --port ${PORT:-8100}"]
