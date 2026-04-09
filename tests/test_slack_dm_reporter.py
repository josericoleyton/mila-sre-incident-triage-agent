"""
Tests for Slack DM to Reporter (Story 5.3).

Covers:
- Block Kit message building for reporter_update DMs
- Block Kit message building for reporter_resolved DMs
- Re-escalation interactive button (Block Kit)
- SlackClient.send_dm adapter: webhook posting, retry on failure
- handle_reporter_update integration: success, failure, re-escalation button
- handle_reporter_resolved integration: success, failure, ticket link
- ReporterNotifier port interface compliance
- Notification model: allow_reescalation field
- API /api/webhooks/slack: Slack interactive payload parsing

Run:
    pytest tests/test_slack_dm_reporter.py -v
"""

import importlib.util
import json
import sys
import types as _types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_NW_ROOT = _PROJECT_ROOT / "services" / "notification-worker"
_API_ROOT = _PROJECT_ROOT / "services" / "api"


# ---------------------------------------------------------------------------
# Module loading helpers (same pattern as scaffold tests)
# ---------------------------------------------------------------------------

def _load_module_raw(name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


from contextlib import contextmanager


@contextmanager
def _notification_worker_context():
    saved = dict(sys.modules)
    saved_path = list(sys.path)

    svc_path = str(_NW_ROOT)
    if svc_path in sys.path:
        sys.path.remove(svc_path)
    sys.path.insert(0, svc_path)

    src_pkg = _types.ModuleType("src")
    src_pkg.__path__ = [str(_NW_ROOT / "src")]
    src_pkg.__package__ = "src"
    sys.modules["src"] = src_pkg

    domain_pkg = _types.ModuleType("src.domain")
    domain_pkg.__path__ = [str(_NW_ROOT / "src" / "domain")]
    domain_pkg.__package__ = "src.domain"
    sys.modules["src.domain"] = domain_pkg

    ports_pkg = _types.ModuleType("src.ports")
    ports_pkg.__path__ = [str(_NW_ROOT / "src" / "ports")]
    sys.modules["src.ports"] = ports_pkg

    adapters_pkg = _types.ModuleType("src.adapters")
    adapters_pkg.__path__ = [str(_NW_ROOT / "src" / "adapters")]
    sys.modules["src.adapters"] = adapters_pkg

    adapters_inbound_pkg = _types.ModuleType("src.adapters.inbound")
    adapters_inbound_pkg.__path__ = [str(_NW_ROOT / "src" / "adapters" / "inbound")]
    sys.modules["src.adapters.inbound"] = adapters_inbound_pkg

    adapters_outbound_pkg = _types.ModuleType("src.adapters.outbound")
    adapters_outbound_pkg.__path__ = [str(_NW_ROOT / "src" / "adapters" / "outbound")]
    sys.modules["src.adapters.outbound"] = adapters_outbound_pkg

    _load_module_raw("src.config", _NW_ROOT / "src" / "config.py")
    _load_module_raw("src.ports.inbound", _NW_ROOT / "src" / "ports" / "inbound.py")
    _load_module_raw("src.ports.outbound", _NW_ROOT / "src" / "ports" / "outbound.py")
    _load_module_raw("src.domain.models", _NW_ROOT / "src" / "domain" / "models.py")
    _load_module_raw(
        "src.adapters.outbound.slack_client",
        _NW_ROOT / "src" / "adapters" / "outbound" / "slack_client.py",
    )
    _load_module_raw("src.domain.services", _NW_ROOT / "src" / "domain" / "services.py")

    try:
        yield
    finally:
        new_keys = set(sys.modules.keys()) - set(saved.keys())
        for k in new_keys:
            del sys.modules[k]
        sys.modules.update(saved)
        sys.path[:] = saved_path


with _notification_worker_context():
    _models = sys.modules["src.domain.models"]
    _services = sys.modules["src.domain.services"]
    _slack_client_mod = sys.modules["src.adapters.outbound.slack_client"]
    _ports_outbound = sys.modules["src.ports.outbound"]

Notification = _models.Notification
NotificationType = _models.NotificationType
build_reporter_update_blocks = _services.build_reporter_update_blocks
build_reporter_resolved_blocks = _services.build_reporter_resolved_blocks
handle_reporter_update = _services.handle_reporter_update
handle_reporter_resolved = _services.handle_reporter_resolved
SlackClient = _slack_client_mod.SlackClient
ReporterNotifier = _ports_outbound.ReporterNotifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reporter_update_payload(**overrides) -> dict:
    base = {
        "type": "reporter_update",
        "incident_id": "inc-200",
        "message": "This does not appear to be a system incident. The error you encountered is a known transient timeout.",
        "confidence": 0.85,
        "allow_reescalation": True,
    }
    base.update(overrides)
    return base


def _reporter_resolved_payload(**overrides) -> dict:
    base = {
        "type": "reporter_resolved",
        "incident_id": "inc-300",
        "title": "NullReferenceException in OrderController.cs",
        "ticket_url": "https://linear.app/team/ENG-42",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Notification model: allow_reescalation field
# ---------------------------------------------------------------------------

class TestNotificationModelReescalationField:
    def test_allow_reescalation_parses_true(self):
        n = Notification(**_reporter_update_payload(allow_reescalation=True))
        assert n.allow_reescalation is True

    def test_allow_reescalation_parses_false(self):
        n = Notification(**_reporter_update_payload(allow_reescalation=False))
        assert n.allow_reescalation is False

    def test_allow_reescalation_defaults_to_none(self):
        n = Notification(type="reporter_update", incident_id="inc-1")
        assert n.allow_reescalation is None


# ---------------------------------------------------------------------------
# Block Kit: reporter_update DM blocks
# ---------------------------------------------------------------------------

class TestBuildReporterUpdateBlocks:
    def test_header_is_incident_update(self):
        n = Notification(**_reporter_update_payload())
        blocks = build_reporter_update_blocks(n)
        header = blocks[0]
        assert header["type"] == "header"
        assert "Incident Update" in header["text"]["text"]

    def test_message_section_contains_explanation(self):
        n = Notification(**_reporter_update_payload())
        blocks = build_reporter_update_blocks(n)
        section = blocks[1]
        assert section["type"] == "section"
        assert "transient timeout" in section["text"]["text"]

    def test_context_shows_confidence_and_incident_id(self):
        n = Notification(**_reporter_update_payload())
        blocks = build_reporter_update_blocks(n)
        ctx = blocks[2]
        assert ctx["type"] == "context"
        text = ctx["elements"][0]["text"]
        assert "0.85" in text
        assert "inc-200" in text

    def test_reescalation_button_when_allowed(self):
        n = Notification(**_reporter_update_payload(allow_reescalation=True))
        blocks = build_reporter_update_blocks(n)
        actions = blocks[3]
        assert actions["type"] == "actions"
        button = actions["elements"][0]
        assert button["type"] == "button"
        assert button["style"] == "danger"
        assert "Re-escalate" in button["text"]["text"]
        assert button["action_id"] == "reescalate_inc-200"
        assert button["value"] == "inc-200"

    def test_no_button_when_reescalation_not_allowed(self):
        n = Notification(**_reporter_update_payload(allow_reescalation=False))
        blocks = build_reporter_update_blocks(n)
        assert len(blocks) == 3
        assert all(b["type"] != "actions" for b in blocks)

    def test_no_button_when_reescalation_none(self):
        n = Notification(**_reporter_update_payload(allow_reescalation=None))
        blocks = build_reporter_update_blocks(n)
        assert len(blocks) == 3

    def test_missing_message_uses_default(self):
        n = Notification(**_reporter_update_payload(message=None))
        blocks = build_reporter_update_blocks(n)
        assert "has been analyzed" in blocks[1]["text"]["text"]

    def test_missing_confidence_shows_na(self):
        n = Notification(**_reporter_update_payload(confidence=None))
        blocks = build_reporter_update_blocks(n)
        text = blocks[2]["elements"][0]["text"]
        assert "N/A" in text


# ---------------------------------------------------------------------------
# Block Kit: reporter_resolved DM blocks
# ---------------------------------------------------------------------------

class TestBuildReporterResolvedBlocks:
    def test_header_is_incident_resolved(self):
        n = Notification(**_reporter_resolved_payload())
        blocks = build_reporter_resolved_blocks(n)
        header = blocks[0]
        assert header["type"] == "header"
        assert "Incident Resolved" in header["text"]["text"]

    def test_message_contains_title_and_celebration(self):
        n = Notification(**_reporter_resolved_payload())
        blocks = build_reporter_resolved_blocks(n)
        section = blocks[1]
        assert "NullReferenceException in OrderController.cs" in section["text"]["text"]
        assert "resolved" in section["text"]["text"]
        assert "🎉" in section["text"]["text"]

    def test_ticket_link_button_present(self):
        n = Notification(**_reporter_resolved_payload())
        blocks = build_reporter_resolved_blocks(n)
        actions = blocks[2]
        assert actions["type"] == "actions"
        button = actions["elements"][0]
        assert button["url"] == "https://linear.app/team/ENG-42"
        assert button["text"]["text"] == "View Ticket"

    def test_no_action_block_when_no_ticket_url(self):
        n = Notification(**_reporter_resolved_payload(ticket_url=None))
        blocks = build_reporter_resolved_blocks(n)
        assert len(blocks) == 2
        assert all(b["type"] != "actions" for b in blocks)

    def test_missing_title_falls_back_to_incident_id(self):
        n = Notification(**_reporter_resolved_payload(title=None))
        blocks = build_reporter_resolved_blocks(n)
        assert "inc-300" in blocks[1]["text"]["text"]


# ---------------------------------------------------------------------------
# SlackClient.send_dm adapter tests
# ---------------------------------------------------------------------------

class TestSlackClientDmAdapter:
    def test_implements_reporter_notifier_port(self):
        assert issubclass(SlackClient, ReporterNotifier)

    def test_warns_when_bot_token_empty(self):
        with patch.object(_slack_client_mod.logger, "warning") as mock_warn:
            SlackClient(bot_token="")
            calls = [c[0][0] for c in mock_warn.call_args_list]
            assert any("SLACK_BOT_TOKEN" in msg for msg in calls)

    @pytest.mark.asyncio
    async def test_send_dm_success(self):
        client = SlackClient(
            bot_token="xoxb-test-token",
        )
        mock_web = AsyncMock()
        mock_web.users_lookupByEmail.return_value = {"user": {"id": "U12345"}}
        mock_web.conversations_open.return_value = {"channel": {"id": "D12345"}}
        mock_web.chat_postMessage.return_value = {"ok": True}
        client._web_client = mock_web

        result = await client.send_dm(
            "user@example.com",
            [{"type": "section", "text": {"type": "mrkdwn", "text": "hello"}}],
            "hello fallback",
        )
        assert result is True
        mock_web.users_lookupByEmail.assert_called_once_with(email="user@example.com")
        mock_web.conversations_open.assert_called_once_with(users=["U12345"])
        mock_web.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_dm_retries_on_failure(self):
        client = SlackClient(
            bot_token="xoxb-test-token",
        )
        mock_web_fail = AsyncMock(side_effect=ConnectionError("unreachable"))
        mock_web_success = AsyncMock()
        mock_web_success.users_lookupByEmail.return_value = {"user": {"id": "U12345"}}
        mock_web_success.conversations_open.return_value = {"channel": {"id": "D12345"}}
        mock_web_success.chat_postMessage.return_value = {"ok": True}

        call_count = 0
        original_web = AsyncMock()

        async def lookup_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("unreachable")
            return {"user": {"id": "U12345"}}

        original_web.users_lookupByEmail = AsyncMock(side_effect=lookup_side_effect)
        original_web.conversations_open = AsyncMock(return_value={"channel": {"id": "D12345"}})
        original_web.chat_postMessage = AsyncMock(return_value={"ok": True})
        client._web_client = original_web

        with patch.object(_slack_client_mod.asyncio, "sleep", new_callable=AsyncMock):
            result = await client.send_dm("user@example.com", [], "text")
            assert result is True

    @pytest.mark.asyncio
    async def test_send_dm_fails_after_max_retries(self):
        client = SlackClient(
            bot_token="xoxb-test-token",
        )
        mock_web = AsyncMock()
        mock_web.users_lookupByEmail.side_effect = Exception("user not found")
        client._web_client = mock_web

        with patch.object(_slack_client_mod.asyncio, "sleep", new_callable=AsyncMock):
            result = await client.send_dm("bad@example.com", [], "text")
            assert result is False

    @pytest.mark.asyncio
    async def test_send_dm_fails_when_no_email(self):
        client = SlackClient(
            bot_token="xoxb-test-token",
        )
        result = await client.send_dm("", [], "text")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_dm_fails_when_bot_token_not_configured(self):
        client = SlackClient(
            bot_token="",
        )
        result = await client.send_dm("user@example.com", [], "text")
        assert result is False


# ---------------------------------------------------------------------------
# handle_reporter_update integration tests
# ---------------------------------------------------------------------------

class TestHandleReporterUpdate:
    @pytest.mark.asyncio
    async def test_sends_dm_blocks_to_slack(self):
        n = Notification(**_reporter_update_payload())
        mock_dm = AsyncMock(return_value=True)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_dm = mock_dm
            await handle_reporter_update(n, "evt-200")

            mock_dm.assert_called_once()
            blocks = mock_dm.call_args[0][1]
            assert len(blocks) == 4  # header, section, context, actions (reescalation)

    @pytest.mark.asyncio
    async def test_passes_event_id_to_adapter(self):
        n = Notification(**_reporter_update_payload())
        mock_dm = AsyncMock(return_value=True)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_dm = mock_dm
            await handle_reporter_update(n, "evt-corr-789")
            assert mock_dm.call_args[1]["event_id"] == "evt-corr-789"

    @pytest.mark.asyncio
    async def test_logs_success(self):
        n = Notification(**_reporter_update_payload())
        mock_dm = AsyncMock(return_value=True)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_dm = mock_dm
            with patch.object(_services.logger, "info") as mock_log:
                await handle_reporter_update(n, "evt-200")
                log_messages = [c[0][0] for c in mock_log.call_args_list]
                assert any("Reporter DM sent" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_logs_failure_does_not_crash(self):
        n = Notification(**_reporter_update_payload())
        mock_dm = AsyncMock(return_value=False)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_dm = mock_dm
            with patch.object(_services.logger, "error") as mock_log:
                await handle_reporter_update(n, "evt-200")
                mock_log.assert_called_once()
                assert "Failed to send" in mock_log.call_args[0][0]

    @pytest.mark.asyncio
    async def test_event_id_in_log_messages(self):
        n = Notification(**_reporter_update_payload())
        mock_dm = AsyncMock(return_value=True)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_dm = mock_dm
            with patch.object(_services.logger, "info") as mock_log:
                await handle_reporter_update(n, "evt-corr-999")
                log_calls = mock_log.call_args_list
                assert any("evt-corr-999" in str(c) for c in log_calls)

    @pytest.mark.asyncio
    async def test_no_reescalation_button_when_false(self):
        n = Notification(**_reporter_update_payload(allow_reescalation=False))
        mock_dm = AsyncMock(return_value=True)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_dm = mock_dm
            await handle_reporter_update(n, "evt-200")
            blocks = mock_dm.call_args[0][1]
            assert len(blocks) == 3  # no actions block

    @pytest.mark.asyncio
    async def test_fallback_text_uses_message(self):
        n = Notification(**_reporter_update_payload())
        mock_dm = AsyncMock(return_value=True)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_dm = mock_dm
            await handle_reporter_update(n, "evt-200")
            fallback = mock_dm.call_args[0][2]
            assert "transient timeout" in fallback


# ---------------------------------------------------------------------------
# handle_reporter_resolved integration tests
# ---------------------------------------------------------------------------

class TestHandleReporterResolved:
    @pytest.mark.asyncio
    async def test_sends_resolved_dm_blocks(self):
        n = Notification(**_reporter_resolved_payload())
        mock_dm = AsyncMock(return_value=True)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_dm = mock_dm
            await handle_reporter_resolved(n, "evt-300")

            mock_dm.assert_called_once()
            blocks = mock_dm.call_args[0][1]
            assert len(blocks) == 3  # header, section, actions (ticket link)

    @pytest.mark.asyncio
    async def test_passes_event_id_to_adapter(self):
        n = Notification(**_reporter_resolved_payload())
        mock_dm = AsyncMock(return_value=True)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_dm = mock_dm
            await handle_reporter_resolved(n, "evt-corr-300")
            assert mock_dm.call_args[1]["event_id"] == "evt-corr-300"

    @pytest.mark.asyncio
    async def test_logs_success(self):
        n = Notification(**_reporter_resolved_payload())
        mock_dm = AsyncMock(return_value=True)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_dm = mock_dm
            with patch.object(_services.logger, "info") as mock_log:
                await handle_reporter_resolved(n, "evt-300")
                log_messages = [c[0][0] for c in mock_log.call_args_list]
                assert any("Resolved DM sent" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_logs_failure_does_not_crash(self):
        n = Notification(**_reporter_resolved_payload())
        mock_dm = AsyncMock(return_value=False)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_dm = mock_dm
            with patch.object(_services.logger, "error") as mock_log:
                await handle_reporter_resolved(n, "evt-300")
                mock_log.assert_called_once()
                assert "Failed to send" in mock_log.call_args[0][0]

    @pytest.mark.asyncio
    async def test_fallback_text_contains_title(self):
        n = Notification(**_reporter_resolved_payload())
        mock_dm = AsyncMock(return_value=True)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_dm = mock_dm
            await handle_reporter_resolved(n, "evt-300")
            fallback = mock_dm.call_args[0][2]
            assert "NullReferenceException" in fallback
            assert "resolved" in fallback

    @pytest.mark.asyncio
    async def test_no_ticket_button_when_no_url(self):
        n = Notification(**_reporter_resolved_payload(ticket_url=None))
        mock_dm = AsyncMock(return_value=True)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_dm = mock_dm
            await handle_reporter_resolved(n, "evt-300")
            blocks = mock_dm.call_args[0][1]
            assert len(blocks) == 2  # no actions block


# ---------------------------------------------------------------------------
# ReporterNotifier port interface compliance
# ---------------------------------------------------------------------------

class TestReporterNotifierPort:
    def test_port_is_abstract(self):
        with pytest.raises(TypeError):
            ReporterNotifier()

    def test_send_dm_is_abstract_method(self):
        assert hasattr(ReporterNotifier, "send_dm")
        assert getattr(ReporterNotifier.send_dm, "__isabstractmethod__", False)


# ---------------------------------------------------------------------------
# API /api/webhooks/slack — Slack interaction payload tests
# ---------------------------------------------------------------------------

class TestSlackWebhookEndpoint:
    """Tests for the API's /api/webhooks/slack endpoint handling Slack interactive payloads."""

    @pytest.fixture
    def api_client(self):
        saved = dict(sys.modules)
        saved_path = list(sys.path)

        svc_path = str(_API_ROOT)
        if svc_path in sys.path:
            sys.path.remove(svc_path)
        sys.path.insert(0, svc_path)

        api_src_pkg = _types.ModuleType("src")
        api_src_pkg.__path__ = [str(_API_ROOT / "src")]
        api_src_pkg.__package__ = "src"
        sys.modules["src"] = api_src_pkg

        api_domain_pkg = _types.ModuleType("src.domain")
        api_domain_pkg.__path__ = [str(_API_ROOT / "src" / "domain")]
        sys.modules["src.domain"] = api_domain_pkg

        api_ports_pkg = _types.ModuleType("src.ports")
        api_ports_pkg.__path__ = [str(_API_ROOT / "src" / "ports")]
        sys.modules["src.ports"] = api_ports_pkg

        api_adapters_pkg = _types.ModuleType("src.adapters")
        api_adapters_pkg.__path__ = [str(_API_ROOT / "src" / "adapters")]
        sys.modules["src.adapters"] = api_adapters_pkg

        api_adapters_inbound_pkg = _types.ModuleType("src.adapters.inbound")
        api_adapters_inbound_pkg.__path__ = [str(_API_ROOT / "src" / "adapters" / "inbound")]
        sys.modules["src.adapters.inbound"] = api_adapters_inbound_pkg

        api_adapters_outbound_pkg = _types.ModuleType("src.adapters.outbound")
        api_adapters_outbound_pkg.__path__ = [str(_API_ROOT / "src" / "adapters" / "outbound")]
        sys.modules["src.adapters.outbound"] = api_adapters_outbound_pkg

        _load_module_raw("src.config", _API_ROOT / "src" / "config.py")

        _load_module_raw("src.ports.inbound", _API_ROOT / "src" / "ports" / "inbound.py")
        _load_module_raw("src.ports.outbound", _API_ROOT / "src" / "ports" / "outbound.py")
        _load_module_raw("src.domain.models", _API_ROOT / "src" / "domain" / "models.py")
        _load_module_raw("src.domain.services", _API_ROOT / "src" / "domain" / "services.py")
        _load_module_raw(
            "src.adapters.inbound.middleware",
            _API_ROOT / "src" / "adapters" / "inbound" / "middleware.py",
        )
        _load_module_raw(
            "src.adapters.outbound.redis_publisher",
            _API_ROOT / "src" / "adapters" / "outbound" / "redis_publisher.py",
        )
        _load_module_raw(
            "src.adapters.inbound.fastapi_routes",
            _API_ROOT / "src" / "adapters" / "inbound" / "fastapi_routes.py",
        )
        _load_module_raw("src.main", _API_ROOT / "src" / "main.py")

        api_main = sys.modules["src.main"]
        from fastapi.testclient import TestClient
        client = TestClient(api_main.app)

        yield client, sys.modules["src.adapters.inbound.fastapi_routes"]

        new_keys = set(sys.modules.keys()) - set(saved.keys())
        for k in new_keys:
            del sys.modules[k]
        sys.modules.update(saved)
        sys.path[:] = saved_path

    def test_slack_form_encoded_payload_publishes_reescalation(self, api_client):
        client, routes_mod = api_client
        mock_pub = AsyncMock()
        mock_pub.publish = AsyncMock(return_value="evt-slack-1")

        with patch.object(routes_mod, "get_publisher", return_value=mock_pub):
            slack_payload = json.dumps({
                "type": "block_actions",
                "actions": [
                    {
                        "action_id": "reescalate_inc-500",
                        "value": "inc-500",
                        "type": "button",
                    }
                ],
                "response_url": "https://hooks.slack.com/actions/respond",
            })

            response = client.post(
                "/api/webhooks/slack",
                data={"payload": slack_payload},
            )
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
            mock_pub.publish.assert_called_once()
            call_args = mock_pub.publish.call_args
            assert call_args[0][0] == "reescalations"
            assert call_args[0][1] == "incident.reescalate"
            assert call_args[0][2]["incident_id"] == "inc-500"

    def test_slack_json_fallback_still_works(self, api_client):
        client, routes_mod = api_client
        mock_pub = AsyncMock()
        mock_pub.publish = AsyncMock(return_value="evt-slack-2")

        with patch.object(routes_mod, "get_publisher", return_value=mock_pub):
            response = client.post(
                "/api/webhooks/slack",
                json={"incident_id": "inc-600", "action": "reescalate"},
            )
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
            mock_pub.publish.assert_called_once()

    def test_slack_form_encoded_missing_payload_field(self, api_client):
        client, routes_mod = api_client
        response = client.post(
            "/api/webhooks/slack",
            data={"something_else": "value"},
        )
        assert response.status_code == 400

    def test_slack_form_encoded_no_reescalation_action(self, api_client):
        client, routes_mod = api_client
        slack_payload = json.dumps({
            "type": "block_actions",
            "actions": [
                {"action_id": "some_other_action", "value": "test"}
            ],
        })
        response = client.post(
            "/api/webhooks/slack",
            data={"payload": slack_payload},
        )
        assert response.status_code == 400

    def test_slack_json_missing_incident_id(self, api_client):
        client, routes_mod = api_client
        response = client.post(
            "/api/webhooks/slack",
            json={"action": "reescalate"},
        )
        assert response.status_code == 400
