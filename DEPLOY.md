# RAG Deployment (Docker + Cloudflare Tunnel + GPU Ollama on host)

This setup publishes your app to the internet while running Ollama on your Windows host GPU.

## What runs where

- Windows host: `ollama serve` (uses your RTX 3060)
- Docker: `app` + `caddy` + `cloudflared`

## 1) Start Ollama on the host

```powershell
ollama serve
```

In a second terminal, ensure models exist:

```powershell
ollama pull qwen2.5:7b-instruct
ollama pull mxbai-embed-large
```

## 2) Configure secrets

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Create a password hash for Caddy basic auth:

```bash
docker run --rm caddy:2 caddy hash-password --plaintext "your-strong-password"
```

Put that result into `BASIC_AUTH_HASH`.

## 3) Start stack

```bash
docker compose up --build -d
```

Get public URL:

```bash
docker compose logs -f cloudflared
```

Look for a line containing `trycloudflare.com`.

## Notes

- URL is random and may change after restart.
- For stable URL, use `cloudflared-token` profile with `CF_TUNNEL_TOKEN`.
- Keep `ollama serve` running on the host.

## Operations

```bash
docker compose logs -f app
docker compose logs -f caddy
docker compose logs -f cloudflared
```
