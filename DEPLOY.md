# RAG Deployment (Docker + Caddy HTTPS)

## 1) Prerequisites

- A public domain/subdomain (example: `rag.yourcompany.com`)
- A host/VM with Docker + Docker Compose
- DNS A record for your domain pointing to the host public IP
- Firewall allows inbound `80/tcp` and `443/tcp`

## 2) Configure environment

Copy `.env.example` to `.env` and edit values:

```bash
cp .env.example .env
```

Generate a basic-auth password hash:

```bash
docker run --rm caddy:2 caddy hash-password --plaintext "your-strong-password"
```

Put that hash into `BASIC_AUTH_HASH` in `.env`.

## 3) Launch stack

```bash
docker compose up --build -d
```

Services:
- `caddy` (public HTTPS edge)
- `app` (internal Streamlit)
- `ollama` (internal model service)

## 4) Verify

- Visit `https://<your-domain>`
- Browser should prompt for username/password
- After login, Streamlit app should load

## 5) Security notes

- `ollama` is no longer published to the public internet
- `app` is internal-only (`expose`, no host port)
- Keep strong basic auth credentials
- For enterprise access control, place this behind VPN/SSO/Zero Trust

## Operations

View logs:

```bash
docker compose logs -f caddy
docker compose logs -f app
docker compose logs -f ollama
```

Restart:

```bash
docker compose restart
```

Update after git pull:

```bash
docker compose up --build -d
```
