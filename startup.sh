#!/bin/bash
# Azure App Service startup script
# Installs the spaCy model if missing, then starts the API

set -e

echo "Checking spaCy model..."
if ! python -c "import en_core_web_lg" 2>/dev/null; then
    echo "Downloading en_core_web_lg..."
    python -m spacy download en_core_web_lg
fi

echo "Starting uvicorn..."
exec uvicorn src.api:api --host 0.0.0.0 --port 8000
