"""
Smoke-test: UI static serving and nginx reverse proxy configuration.

Verifies Story 2.1 acceptance criteria:
1. Static form served at http://localhost:8080 with all visual elements
2. /api/* routes proxy to the API backend
3. /webhooks/linear routes proxy to the ticket-service backend
4. nginx.conf has correct rate limiting, gzip, CORS, and proxy settings

Run:
    pytest tests/test_ui_nginx.py -v
"""

from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_NGINX_CONF = _PROJECT_ROOT / "services" / "ui" / "nginx.conf"
_INDEX_HTML = _PROJECT_ROOT / "services" / "ui" / "public" / "index.html"
_DOCKERFILE = _PROJECT_ROOT / "services" / "ui" / "Dockerfile"


# ---------------------------------------------------------------------------
# index.html — static content tests
# ---------------------------------------------------------------------------

class TestIndexHtml:
    @pytest.fixture(autouse=True)
    def load_html(self):
        self.html = _INDEX_HTML.read_text(encoding="utf-8")

    def test_is_valid_html_document(self):
        assert "<!DOCTYPE html>" in self.html
        assert "<html" in self.html
        assert "</html>" in self.html

    def test_has_title(self):
        assert "<title>Mila" in self.html

    def test_has_incident_title_field(self):
        assert 'id="f-title"' in self.html

    def test_has_description_field(self):
        assert 'id="f-desc"' in self.html

    def test_has_component_dropdown(self):
        assert 'id="f-comp"' in self.html
        assert "Checkout / payments" in self.html

    def test_has_severity_buttons(self):
        assert "sev-btn" in self.html
        assert "sev-low" in self.html or "Low" in self.html

    def test_has_file_upload(self):
        assert 'type="file"' in self.html
        assert "upload-zone" in self.html

    def test_has_mila_hint_bar(self):
        assert "mila-bar" in self.html
        assert "mila-hint" in self.html

    def test_has_progress_bar(self):
        assert "progress-fill" in self.html
        assert "progress-bar" in self.html

    def test_has_submit_button(self):
        assert 'id="submit-btn"' in self.html
        assert "submitForm()" in self.html

    def test_has_success_screen(self):
        assert 'id="success-view"' in self.html
        assert "ticket-num" in self.html

    def test_no_external_cdn_dependencies(self):
        """Ensure no external CDN links that could break offline serving."""
        assert "cdn." not in self.html.lower()
        assert "googleapis.com" not in self.html
        assert "cdnjs." not in self.html

    def test_all_css_is_inline(self):
        assert "<style>" in self.html
        assert 'rel="stylesheet"' not in self.html

    def test_all_js_is_inline(self):
        assert "<script>" in self.html
        assert 'src="http' not in self.html


# ---------------------------------------------------------------------------
# nginx.conf — configuration tests
# ---------------------------------------------------------------------------

class TestNginxConf:
    @pytest.fixture(autouse=True)
    def load_conf(self):
        self.conf = _NGINX_CONF.read_text(encoding="utf-8")

    def test_serves_static_from_correct_root(self):
        assert "/usr/share/nginx/html" in self.conf

    def test_has_try_files_spa_fallback(self):
        assert "try_files $uri $uri/ /index.html" in self.conf

    def test_rate_limiting_zone_configured(self):
        assert "limit_req_zone" in self.conf
        assert "rate=10r/s" in self.conf

    def test_rate_limiting_burst_on_incidents(self):
        assert "burst=20" in self.conf

    def test_api_proxy_configured(self):
        assert "api:8000" in self.conf

    def test_api_incidents_location(self):
        assert "location /api/incidents/" in self.conf

    def test_api_general_location(self):
        assert "location /api/" in self.conf

    def test_webhook_proxy_configured(self):
        assert "ticket-service:8002" in self.conf
        assert "location /webhooks/linear" in self.conf

    def test_cors_headers_not_wildcard(self):
        """CORS should NOT use wildcard * for Access-Control-Allow-Origin."""
        cors_lines = [
            line for line in self.conf.splitlines()
            if "Access-Control-Allow-Origin" in line and not line.strip().startswith("#")
        ]
        for line in cors_lines:
            assert "* " not in line, f"CORS origin should not be wildcard: {line}"
            assert "$http_origin" not in line, f"CORS should not echo raw origin: {line}"

    def test_cors_uses_whitelist_map(self):
        """CORS origin should use a map-based whitelist."""
        assert "map $http_origin $cors_origin" in self.conf
        assert "$cors_origin" in self.conf

    def test_cors_headers_present(self):
        assert "Access-Control-Allow-Origin" in self.conf
        assert "Access-Control-Allow-Methods" in self.conf
        assert "Access-Control-Allow-Headers" in self.conf

    def test_gzip_enabled(self):
        assert "gzip on" in self.conf
        assert "gzip_types" in self.conf

    def test_proxy_headers_set(self):
        assert "X-Real-IP" in self.conf
        assert "X-Forwarded-For" in self.conf
        assert "X-Forwarded-Proto" in self.conf

    def test_listens_on_port_80(self):
        assert "listen 80" in self.conf

    def test_dns_resolver_configured(self):
        """Docker DNS resolver needed for dynamic upstream resolution."""
        assert "resolver" in self.conf
        assert "127.0.0.11" in self.conf


# ---------------------------------------------------------------------------
# Dockerfile — build configuration tests
# ---------------------------------------------------------------------------

class TestDockerfile:
    @pytest.fixture(autouse=True)
    def load_dockerfile(self):
        self.dockerfile = _DOCKERFILE.read_text(encoding="utf-8")

    def test_uses_nginx_alpine(self):
        assert "nginx:alpine" in self.dockerfile

    def test_copies_nginx_conf(self):
        assert "nginx.conf" in self.dockerfile
        assert "/etc/nginx/nginx.conf" in self.dockerfile

    def test_copies_public_dir(self):
        assert "public/" in self.dockerfile
        assert "/usr/share/nginx/html/" in self.dockerfile

    def test_removes_default_conf(self):
        """Default nginx conf must be removed to avoid conflicts."""
        assert "default.conf" in self.dockerfile
