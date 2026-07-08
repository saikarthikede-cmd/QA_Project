# Generic image for the 6 RAG apps (app1_resume_screener .. app6_data_analyst).
# Built once per app via docker-compose build args (APP_DIR, PORT).
FROM python:3.11-slim
WORKDIR /app

# CPU-only torch: sentence-transformers pulls the full CUDA wheel by default
# (~2GB) which is wasted on a CPU-only embedding model in 6 separate images.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
ARG APP_DIR
COPY ${APP_DIR}/ ./${APP_DIR}/

WORKDIR /app/${APP_DIR}
ARG PORT=8000
ENV PORT=${PORT}
EXPOSE ${PORT}
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
