# RAG Deployment (Docker + Cloudflare Tunnel + Basic Auth)

This setup publishes your local Docker stack to the internet without opening router ports.

## What you get

- `ollama` for local models
- `app` for Streamlit
- `caddy` for basic-auth protection
- `cloudflared` for public HTTPS URL

## 1) Configure secrets

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Create a password hash for Caddy basic auth:

```bash
docker run --rm caddy:2 caddy hash-password --plaintext "your-strong-password"
```

Put that result into `BASIC_AUTH_HASH`.

## 2) Start with free Cloudflare URL (no paid domain)

```bash
docker compose up --build -d
```

Get the public URL:

```bash
docker compose logs -f cloudflared
```

Look for a line containing `trycloudflare.com`.

Share that URL with your team. They will see a username/password prompt first.

## 3) Important behavior of free URL mode

- URL is random and may change on restart/redeploy.
- Good for pilots and internal testing.
- For stable company URL, use token mode below.

## 4) Optional: stable URL mode (Cloudflare account + tunnel token)

If you later add a domain in Cloudflare:

1. Create a named tunnel in Cloudflare Zero Trust dashboard.
2. Set public hostname (example: `rag.yourcompany.com`) to `http://caddy:80`.
3. Copy tunnel token into `.env` as `CF_TUNNEL_TOKEN`.
4. Run token profile:

```bash
docker compose up -d --profile token cloudflared-token
```

5. Stop quick tunnel service:

```bash
docker compose stop cloudflared
```

## Operations

View logs:

```bash
docker compose logs -f app
docker compose logs -f ollama
docker compose logs -f caddy
docker compose logs -f cloudflared
```

Restart all:

```bash
docker compose restart
```

Update after git pull:

```bash
docker compose up --build -d
```
