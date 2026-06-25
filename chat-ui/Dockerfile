# Optimal chat — our own branded chat surface (replaces Open WebUI on the chat-host).
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY static ./static

# Bound to 0.0.0.0 INSIDE the container; the compose port maps it to 127.0.0.1
# on the host only (the load-bearing boundary — see chat-host docker-compose.yml).
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health').status==200 else 1)"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
