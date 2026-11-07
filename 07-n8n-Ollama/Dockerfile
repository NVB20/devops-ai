# The step 07 chatbot. Built from the repo root (it needs knowledge-base/ too):
#   docker compose build      or      docker build -f 07-n8n-Ollama/Dockerfile .
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FASTEMBED_CACHE_PATH=/models \
    KB_DIR=/knowledge-base

WORKDIR /app

# Dependencies first: this layer is rebuilt only when requirements.txt changes
COPY 07-n8n-Ollama/app/requirements.txt app/requirements.txt
RUN pip install -r app/requirements.txt

# Not root. /models is the user's, so the embedding model can be downloaded into it.
RUN useradd --create-home chatbot && mkdir /models && chown chatbot /models
USER chatbot

# The embedding model (~90 MB) is downloaded now, once, instead of on every container start
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2')"

COPY knowledge-base /knowledge-base
COPY 07-n8n-Ollama/app app
COPY 07-n8n-Ollama/tests tests

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
