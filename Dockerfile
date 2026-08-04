FROM python:3.12-slim

# Unbuffered output so logs appear immediately under docker logs.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies first so edits to source do not invalidate this layer.
COPY ai-agent-discovery/requirements.txt ai-agent-discovery/requirements.txt
RUN pip install --no-cache-dir -r ai-agent-discovery/requirements.txt

COPY ai-agent-discovery/ ai-agent-discovery/
COPY data/agents.json data/agents.json

# Run as a non-root user; it needs to write the FAISS index under data/.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/data/faiss_index \
    && chown -R app:app /app
USER app

# Ollama runs outside this container, so localhost would resolve to the
# container itself. Bind to all interfaces since only Docker's network sees it.
ENV HOST=0.0.0.0 \
    PORT=5000 \
    OLLAMA_BASE_URL=http://host.docker.internal:11434

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:5000/api/health').status==200 else 1)"

CMD ["python", "ai-agent-discovery/frontend/app.py"]
