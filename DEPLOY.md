# RAG Deployment (Docker)

## 1) Run locally with Docker

```bash
docker compose up --build -d
```

App URL: `http://localhost:8501`

View logs:

```bash
docker compose logs -f app
docker compose logs -f ollama
```

Stop:

```bash
docker compose down
```

## 2) Make it available to coworkers (recommended)

Deploy this repo on an always-on Linux VM (cloud or on-prem), then run:

```bash
git clone https://github.com/wompuus/RAG.git
cd RAG
docker compose up --build -d
```

Open firewall ports:
- `8501/tcp` (Streamlit)
- optional `11434/tcp` only if you need direct Ollama API access (usually keep closed)

## 3) Production hardening

- Put Nginx/Caddy in front of Streamlit with HTTPS.
- Restrict access via company VPN, SSO, or IP allowlist.
- Keep `ollama_data` volume persistent so models are not re-downloaded.

## Model defaults

- Chat model: `qwen2.5:7b-instruct`
- Embedding model: `mxbai-embed-large`

Override on startup:

```bash
OLLAMA_MODEL=qwen2.5:14b-instruct OLLAMA_EMBED_MODEL=mxbai-embed-large docker compose up -d
```
