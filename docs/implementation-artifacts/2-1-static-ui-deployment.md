# Story 2.1: Static UI Deployment with nginx

> **Epic:** 2 — Incident Submission Experience (UI + API)
> **Status:** complete
> **Priority:** 🟠 High — UI path priority workstream
> **Depends on:** Story 1.1
> **FRs:** UX1, UX2, UX3, UX4, UX5, UX6, UX7

## Story

**As a** reporter,
**I want** to access the incident submission form through a web browser,
**So that** I can begin reporting an incident without any setup or authentication.

## Acceptance Criteria

**Given** the existing `docs/mila_ui_final_v1.html` static form
**When** the developer copies it to `services/ui/public/index.html`
**Then** the file is served by nginx on port 8080 at the root path `/`

**Given** the nginx configuration
**When** a user navigates to `http://localhost:8080`
**Then** the incident submission form loads with all visual elements (title, description, component dropdown, severity buttons, file upload, Mila hint bar, progress bar)
**And** the form is fully interactive (typing, selecting, uploading preview) even without a backend connected

**Given** the nginx reverse proxy configuration
**When** requests are made to `/api/*`
**Then** they are proxied to the API service at `api:8000`
**And** requests to `/webhooks/linear` are proxied to `ticket-service:8002`
**And** rate limiting is configured on `/api/incidents` (e.g., 10 req/s burst 20)
**And** CORS headers restrict origins appropriately

## Tasks / Subtasks

- [x] **1. Copy and adapt UI HTML**
  - Copy `docs/mila_ui_final_v1.html` to `services/ui/public/index.html`
  - Verify all inline CSS and JS work correctly when served from nginx
  - Ensure no external CDN dependencies that could break offline

- [x] **2. Configure nginx.conf**
  - Serve static files from `/usr/share/nginx/html`
  - Reverse proxy `/api/` → `http://api:8000/api/`
  - Reverse proxy `/webhooks/linear` → `http://ticket-service:8002/webhooks/linear`
  - Rate limiting zone on `/api/incidents`: 10 req/s, burst 20
  - CORS headers: `Access-Control-Allow-Origin` restricted to known origins
  - Gzip compression for HTML/CSS/JS
  - Custom error pages (optional)

- [x] **3. Update UI Dockerfile**
  - Replace placeholder in `services/ui/Dockerfile` to copy `public/` and `nginx.conf` properly
  - Use `nginx:alpine` base image

- [x] **4. Verify end-to-end serving**
  - `docker compose up ui` serves the form at `http://localhost:8080`
  - Form is fully interactive without backend (client-side only)
  - Reverse proxy routes forward to backends (verified via API logs)

### Review Findings

- [x] [Review][Patch] CORS `$http_origin` reflects any origin — fixed with `map` whitelist [`services/ui/nginx.conf`]
- [x] [Review][Patch] Rate limit bypass via trailing slash on `/api/incidents/` — fixed [`services/ui/nginx.conf`]
- [x] [Review][Patch] Unused `import re` in test file — removed [`tests/test_ui_nginx.py`]
- [x] [Review][Defer] Dynamic upstream variables disable nginx connection pooling [`services/ui/nginx.conf`] — deferred, intentional trade-off for graceful startup
- [x] [Review][Defer] X-Real-IP header spoofable by client [`services/ui/nginx.conf`] — deferred, pre-existing pattern

## Dev Notes

### Architecture Guardrails
- **Only port 8080 exposed externally** from Docker network (AR6). Langfuse on 3000 is the only other external port.
- **nginx is the API gateway** — all external HTTP traffic flows through nginx. No direct access to backend services from outside Docker.
- **Rate limiting** on `/api/incidents` prevents abuse (NFR20, FR33).

### UI HTML Details (from analysis of `docs/mila_ui_final_v1.html`)
- Fields: title (text, required), description (textarea), component (select, optional), severity (custom CSS buttons — no value captured yet), file upload (optional, accepts image/video/log/txt, 50MB)
- Reporter hardcoded as "Ana Botero" in the footer
- `submitForm()` is client-side only — no network request yet (Story 2.3 wires it up)
- Success screen shows random ticket ID (Story 2.3 replaces with API response)

### nginx.conf Pattern
```nginx
upstream api_backend {
    server api:8000;
}
upstream ticket_backend {
    server ticket-service:8002;
}
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://api_backend;
        # CORS + proxy headers
    }

    location /webhooks/linear {
        proxy_pass http://ticket_backend;
    }
}
```

### Key Reference Files
- UI source: `docs/mila_ui_final_v1.html`
- Architecture doc: `docs/planning-artifacts/architecture.md` — nginx config, port mapping, security

## File List

- `services/ui/public/index.html` — replaced placeholder with full incident form from `docs/mila_ui_final_v1.html`
- `services/ui/nginx.conf` — updated rate limiting (10r/s burst 20), CORS (restricted origins), gzip, Docker DNS resolver
- `services/ui/Dockerfile` — added removal of default.conf to prevent server block conflict
- `docker-compose.yml` — removed `depends_on` for api/ticket-service so UI can start independently
- `tests/test_ui_nginx.py` — 32 new tests covering index.html content, nginx.conf config, and Dockerfile setup

## Change Log

- 2026-04-08: Story 2.1 implemented — static UI deployment with nginx reverse proxy
- 2026-04-08: Code review patches — CORS whitelist map, rate limit trailing slash fix, removed unused import

## Chat Command Log

### Implementation Decisions
- Wrapped the HTML fragment from `mila_ui_final_v1.html` in a proper `<!DOCTYPE html>` document structure
- Used Docker DNS resolver (`127.0.0.11`) with variable-based `proxy_pass` for dynamic upstream resolution — allows nginx to start even when backend services aren't running
- Removed nginx default.conf from alpine image to prevent server block conflicts (default matches `localhost` before our `server_name _`)
- Removed `depends_on` from UI service in docker-compose so `docker compose up ui` works without building api/ticket-service
- CORS `Access-Control-Allow-Origin` uses `$http_origin` instead of wildcard `*` for security
- Rate limiting: 10 req/s with burst 20 on `/api/incidents` per story spec (was incorrectly 10r/m burst 5)
