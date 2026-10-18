# Single-machine deployment (Cloudflare Tunnel + nginx)

How the platform is published from one machine at
**https://aiobs.tudoroprea.me** without opening any inbound ports:

```
Teams ──https──▶ aiobs.tudoroprea.me        (Cloudflare edge: DNS, TLS, proxy)
                      │  outbound-only tunnel
                      ▼
               cloudflared (host)
                      ▼
      nginx @ 127.0.0.1:8081                (ops/nginx/aiobs.conf; plain HTTP)
        ├── /v1/traces, /api/v1/traces, /health ─▶ backend   @ 127.0.0.1:8000
        └── /                                   ─▶ dashboard @ 127.0.0.1:8080
                                                     └── /api/ ─▶ backend (compose network)
```

TLS is terminated by Cloudflare and the tunnel dials out, so the machine
needs no public IP, no port forwarding and no certificates. Everything the
compose stack publishes is bound to loopback by
[`docker-compose.local.yml`](../docker-compose.local.yml).

## Prerequisites

- Docker + the compose plugin (`!override` needs Compose v2.24+; v5 works)
- nginx installed on the host
- [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
- the `tudoroprea.me` zone on your Cloudflare account

## 1. Secrets

```bash
cp .env.example .env
openssl rand -hex 32    # run twice: AIOBS_ADMIN_API_KEY and AIOBS_JWT_SECRET
```

Fill `.env` with real values (it is gitignored). The overridden stack refuses
to start without them — the demo secrets in `docker-compose.yml` (`admin`,
`dev-secret-…`, `admin-pass-123`) must never face the internet.

Notes:

- `AIOBS_ADMIN_PASSWORD` seeds the bootstrap admin **only when the account is
  first created**. If the stack was already booted with the demo admin, rotate
  the password after step 2 (see section 5).
- The Postgres password stays at the demo value: the port is loopback-only.
  Changing `POSTGRES_PASSWORD` later also needs `ALTER USER` — env vars only
  apply when the volume is first initialized.

## 2. Start the stack (loopback only)

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

Verify from the host:

```bash
curl -s http://127.0.0.1:8000/health     # {"status":"ok","version":...}
curl -sI http://127.0.0.1:8080 | head -1 # HTTP/1.1 200 OK
```

The dashboard session cookie is marked `Secure` in this deployment, so log in
through the public URL (section 6) rather than `http://127.0.0.1:8080`.

## 3. nginx

```bash
sudo cp ops/nginx/aiobs.conf /etc/nginx/sites-available/aiobs.conf
sudo ln -sf ../sites-available/aiobs.conf /etc/nginx/sites-enabled/aiobs.conf
sudo nginx -t && sudo systemctl reload nginx

curl -s http://127.0.0.1:8081/health     # reaches the backend via nginx
```

## 4. Cloudflare Tunnel

```bash
cloudflared tunnel login                 # browser: authorize tudoroprea.me
cloudflared tunnel create aiobs          # prints the tunnel UUID
cloudflared tunnel route dns aiobs aiobs.tudoroprea.me
```

Put the UUID into [`ops/cloudflared/config.yml`](cloudflared/config.yml)
(`tunnel:` and `credentials-file:`), then test in the foreground:

```bash
cloudflared tunnel --config ops/cloudflared/config.yml run
```

From another terminal:

```bash
curl -s https://aiobs.tudoroprea.me/health
```

Install as a service so it survives reboots:

```bash
sudo mkdir -p /etc/cloudflared
sudo cp ops/cloudflared/config.yml /etc/cloudflared/config.yml
sudo cp ~/.cloudflared/<TUNNEL-UUID>.json /etc/cloudflared/
# edit /etc/cloudflared/config.yml:
#   credentials-file: /etc/cloudflared/<TUNNEL-UUID>.json
sudo cloudflared --config /etc/cloudflared/config.yml service install
sudo systemctl enable --now cloudflared
systemctl status cloudflared
```

## 5. First admin & project keys

If the admin was already created with the demo password, rotate it now (both
calls use the admin key; the new password is returned once):

```bash
set -a; . ./.env; set +a
curl -s http://127.0.0.1:8000/api/v1/users -H "x-admin-key: $AIOBS_ADMIN_API_KEY"
curl -s -X POST http://127.0.0.1:8000/api/v1/users/<user_id>/reset-password \
  -H "x-admin-key: $AIOBS_ADMIN_API_KEY"
```

Mint a project + ingest key for a team (department/team are created on the
spot if missing; the plaintext key is shown once):

```bash
curl -s http://127.0.0.1:8000/api/v1/projects \
  -H "x-admin-key: $AIOBS_ADMIN_API_KEY" \
  -H 'content-type: application/json' \
  -d '{"name":"team-a-agent","department_name":"Engineering","team_name":"Team A"}'
```

## 6. Handing ingest to a team

Endpoint + key, nothing else:

```bash
export AI_OBSERVABILITY_ENDPOINT=https://aiobs.tudoroprea.me
export AI_OBSERVABILITY_API_KEY=<the project key>
```

The SDK appends `/v1/traces` itself; plain OTLP exporters can target
`https://aiobs.tudoroprea.me/v1/traces` with
`authorization: Bearer <the project key>`.

Smoke test with the repo's mock workflows:

```bash
cd sdk && uv sync --group dev
uv run aiobs-mock --endpoint https://aiobs.tudoroprea.me --api-key <the project key>
```

## Operations notes

- **The machine is the server**: keep it awake while ingest matters; when it
  sleeps the tunnel drops and in-flight spans are lost.
- **Rotating keys**: dashboard → a project's page → Keys, or the admin-key
  calls above. Prefer rotate over share.
- **Cloudflare sits in the data path** (TLS terminates at the edge, the
  tunnel re-encrypts to the machine). With prompt capture enabled, prompts
  leave the machine.
- **Backups**: everything lives in the compose `pgdata` volume.
- **Never publish the compose ports beyond loopback** — the only public path
  is the tunnel.
