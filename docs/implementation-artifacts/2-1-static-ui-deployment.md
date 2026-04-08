# Story 2.1: Static UI Deployment with nginx

> **Epic:** 2 — Incident Submission Experience (UI + API)
> **Status:** ready-for-dev
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

- [ ] **1. Copy and adapt UI HTML**
  - Copy `docs/mila_ui_final_v1.html` to `services/ui/public/index.html`
  - Verify all inline CSS and JS work correctly when served from nginx
  - Ensure no external CDN dependencies that could break offline

- [ ] **2. Configure nginx.conf**
  - Serve static files from `/usr/share/nginx/html`
  - Reverse proxy `/api/` → `http://api:8000/api/`
  - Reverse proxy `/webhooks/linear` → `http://ticket-service:8002/webhooks/linear`
  - Rate limiting zone on `/api/incidents`: 10 req/s, burst 20
  - CORS headers: `Access-Control-Allow-Origin` restricted to known origins
  - Gzip compression for HTML/CSS/JS
  - Custom error pages (optional)

- [ ] **3. Update UI Dockerfile**
  - Replace placeholder in `services/ui/Dockerfile` to copy `public/` and `nginx.conf` properly
  - Use `nginx:alpine` base image

- [ ] **4. Verify end-to-end serving**
  - `docker compose up ui` serves the form at `http://localhost:8080`
  - Form is fully interactive without backend (client-side only)
  - Reverse proxy routes return 502 (expected — backend not running yet) rather than 404

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

## Chat Command Log

*Dev agent: record your implementation commands and decisions here.*
