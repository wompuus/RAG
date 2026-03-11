#!/usr/bin/env bash
set -euo pipefail

echo "Waiting for Ollama at ${OLLAMA_HOST:-http://ollama:11434} ..."
python - <<'PY'
import os
import time
import urllib.request
import urllib.error

host = os.getenv("OLLAMA_HOST", "http://ollama:11434").rstrip("/")
url = f"{host}/api/tags"

for _ in range(120):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            if r.status == 200:
                print("Ollama is ready")
                break
    except Exception:
        pass
    time.sleep(2)
else:
    raise SystemExit("Ollama did not become ready in time")
PY

exec streamlit run main.py --server.address 0.0.0.0 --server.port 8501
