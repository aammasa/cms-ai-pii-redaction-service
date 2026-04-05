FROM python:3.13-slim

WORKDIR /app

# Install system dependencies for pdfplumber / spacy
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download English spaCy model (required)
RUN python -m spacy download en_core_web_lg

# Copy application source
COPY src/       ./src/
COPY mcp_server/ ./mcp_server/
COPY main.py    mcp_main.py ./

# Create data directory for custom pattern persistence
RUN mkdir -p /app/data

# Default: REST API (override in docker-compose.yml for MCP)
CMD ["uvicorn", "src.api:api", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
