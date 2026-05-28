# Compliance MCP server (read-only — ADR-005)
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY data/ ./data/

# Build the read-only POA&M db from the seed SQL at image build time.
RUN python -c "import sqlite3; sqlite3.connect('/app/data/poams.db').executescript(open('/app/data/seed_poams.sql').read())"

ENV MCP_TRANSPORT=streamable-http \
    MCP_DATA_DIR=/app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -m src.server --health || exit 1

CMD ["python", "-m", "src.server"]
