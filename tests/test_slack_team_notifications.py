"""
Tests for Slack Team Channel Notifications (Story 5.2).

Covers:
- Block Kit message building (severity emojis, fields, actions, source labels)
- SlackClient adapter: webhook posting, retry on failure, structured error logging
- handle_team_alert integration: success and failure paths
- TeamNotifier port interface compliance
- Notification model: title and source_type fields

Run:
    pytest tests/test_slack_team_notifications.py -v
"""

import importlib.util
import sys
import types as _types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_NW_ROOT = _PROJECT_ROOT / "services" / "notification-worker"


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
    _load_module_raw(
        "src.adapters.inbound.redis_consumer",
        _NW_ROOT / "src" / "adapters" / "inbound" / "redis_consumer.py",
    )
    _load_module_raw(
        "src.adapters.outbound.redis_publisher",
        _NW_ROOT / "src" / "adapters" / "outbound" / "redis_publisher.py",
    )

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
build_team_alert_blocks = _services.build_team_alert_blocks
handle_team_alert = _services.handle_team_alert
SlackClient = _slack_client_mod.SlackClient
TeamNotifier = _ports_outbound.TeamNotifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_envelope(event_type: str, source: str, payload: dict) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "payload": payload,
    }


def _team_alert_payload(**overrides) -> dict:
    base = {
        "type": "team_alert",
        "incident_id": "inc-100",
        "title": "NullReferenceException in OrderController.cs",
        "ticket_url": "https://linear.app/team/ENG-42",
        "severity": "critical",
        "component": "Ordering",
        "summary": "NullReferenceException when order items collection is empty",
        "source_type": "user_reported",
        "confidence": 0.87,
        "reporter_email": "user@example.com",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Notification model field tests
# ---------------------------------------------------------------------------

class TestNotificationModelNewFields:
    def test_title_field_parses(self):
        n = Notification(**_team_alert_payload())
        assert n.title == "NullReferenceException in OrderController.cs"

    def test_source_type_field_parses(self):
        n = Notification(**_team_alert_payload())
        assert n.source_type == "user_reported"

    def test_title_defaults_to_none(self):
        n = Notification(type="team_alert", incident_id="inc-1")
        assert n.title is None

    def test_source_type_defaults_to_none(self):
        n = Notification(type="team_alert", incident_id="inc-1")
        assert n.source_type is None


# ---------------------------------------------------------------------------
# Block Kit message building tests
# ---------------------------------------------------------------------------

class TestBuildTeamAlertBlocks:
    def test_header_contains_severity_emoji_component_and_title(self):
        n = Notification(**_team_alert_payload())
        blocks = build_team_alert_blocks(n)
        header = blocks[0]
        assert header["type"] == "header"
        assert "🔴 [P1] Ordering: NullReferenceException in OrderController.cs" == header["text"]["text"]

    def test_fields_section_has_reporter(self):
        n = Notification(**_team_alert_payload())
        blocks = build_team_alert_blocks(n)
        fields = blocks[1]
        assert fields["type"] == "section"
        field_texts = [f["text"] for f in fields["fields"]]
        assert any("Reporter: user@example.com" in t for t in field_texts)

    def test_root_cause_section(self):
        n = Notification(**_team_alert_payload())
        blocks = build_team_alert_blocks(n)
        root_cause = blocks[2]
        assert root_cause["type"] == "section"
        assert "NullReferenceException when order items" in root_cause["text"]["text"]

    def test_action_button_links_to_ticket(self):
        n = Notification(**_team_alert_payload())
        blocks = build_team_alert_blocks(n)
        actions = blocks[3]
        assert actions["type"] == "actions"
        button = actions["elements"][0]
        assert button["type"] == "button"
        assert button["url"] == "https://linear.app/team/ENG-42"
        assert button["text"]["text"] == "View Ticket"

    def test_no_action_block_when_no_ticket_url(self):
        n = Notification(**_team_alert_payload(ticket_url=None))
        blocks = build_team_alert_blocks(n)
        assert len(blocks) == 3
        assert all(b["type"] != "actions" for b in blocks)

    def test_severity_high_emoji(self):
        n = Notification(**_team_alert_payload(severity="high"))
        blocks = build_team_alert_blocks(n)
        assert "🟠 [P2]" in blocks[0]["text"]["text"]

    def test_severity_medium_emoji(self):
        n = Notification(**_team_alert_payload(severity="medium"))
        blocks = build_team_alert_blocks(n)
        assert "🟡 [P3]" in blocks[0]["text"]["text"]

    def test_severity_low_emoji(self):
        n = Notification(**_team_alert_payload(severity="low"))
        blocks = build_team_alert_blocks(n)
        assert "🔵 [P4]" in blocks[0]["text"]["text"]

    def test_unknown_severity_uses_white_circle(self):
        n = Notification(**_team_alert_payload(severity="unknown"))
        blocks = build_team_alert_blocks(n)
        assert "⚪" in blocks[0]["text"]["text"]

    def test_none_severity_uses_white_circle(self):
        n = Notification(**_team_alert_payload(severity=None))
        blocks = build_team_alert_blocks(n)
        assert "⚪" in blocks[0]["text"]["text"]

    def test_p1_severity_format(self):
        n = Notification(**_team_alert_payload(severity="P1"))
        blocks = build_team_alert_blocks(n)
        assert "🔴 [P1]" in blocks[0]["text"]["text"]

    def test_p2_severity_format(self):
        n = Notification(**_team_alert_payload(severity="P2"))
        blocks = build_team_alert_blocks(n)
        assert "🟠 [P2]" in blocks[0]["text"]["text"]

    def test_proactive_source_type_shows_otel_detection(self):
        n = Notification(**_team_alert_payload(source_type="systemIntegration"))
        blocks = build_team_alert_blocks(n)
        field_texts = [f["text"] for f in blocks[1]["fields"]]
        assert any("Detected by Mila via OpenTelemetry" in t for t in field_texts)

    def test_user_reported_source_type_shows_reporter_email(self):
        n = Notification(**_team_alert_payload(source_type="user_reported"))
        blocks = build_team_alert_blocks(n)
        field_texts = [f["text"] for f in blocks[1]["fields"]]
        assert any("Reporter: user@example.com" in t for t in field_texts)

    def test_none_source_type_defaults_to_reporter(self):
        n = Notification(**_team_alert_payload(source_type=None))
        blocks = build_team_alert_blocks(n)
        field_texts = [f["text"] for f in blocks[1]["fields"]]
        assert any("Reporter:" in t for t in field_texts)

    def test_missing_title_falls_back_to_incident_id(self):
        n = Notification(**_team_alert_payload(title=None))
        blocks = build_team_alert_blocks(n)
        assert "inc-100" in blocks[0]["text"]["text"]

    def test_missing_component_shows_unknown_in_header(self):
        n = Notification(**_team_alert_payload(component=None))
        blocks = build_team_alert_blocks(n)
        assert "Unknown:" in blocks[0]["text"]["text"]

    def test_missing_summary_shows_fallback(self):
        n = Notification(**_team_alert_payload(summary=None))
        blocks = build_team_alert_blocks(n)
        assert "No summary available" in blocks[2]["text"]["text"]

    def test_confidence_hidden_when_70_or_below(self):
        n = Notification(**_team_alert_payload(confidence=0.70))
        blocks = build_team_alert_blocks(n)
        field_texts = [f["text"] for f in blocks[1]["fields"]]
        assert not any("Confidence" in t for t in field_texts)

    def test_confidence_not_shown_in_fields(self):
        n = Notification(**_team_alert_payload(confidence=0.87))
        blocks = build_team_alert_blocks(n)
        field_texts = [f["text"] for f in blocks[1]["fields"]]
        assert not any("Confidence" in t for t in field_texts)

    def test_confidence_hidden_when_none(self):
        n = Notification(**_team_alert_payload(confidence=None))
        blocks = build_team_alert_blocks(n)
        field_texts = [f["text"] for f in blocks[1]["fields"]]
        assert not any("Confidence" in t for t in field_texts)

    def test_root_cause_not_truncated(self):
        long_summary = "x" * 400
        n = Notification(**_team_alert_payload(summary=long_summary))
        blocks = build_team_alert_blocks(n)
        root_cause_text = blocks[2]["text"]["text"]
        # Full summary included without truncation
        assert "x" * 400 in root_cause_text
        assert not root_cause_text.endswith("...")


# ---------------------------------------------------------------------------
# SlackClient adapter tests
# ---------------------------------------------------------------------------

class TestSlackClientAdapter:
    def test_implements_team_notifier_port(self):
        assert issubclass(SlackClient, TeamNotifier)

    def test_warns_when_bot_token_empty(self):
        with patch.object(_slack_client_mod.logger, "warning") as mock_warn:
            SlackClient(bot_token="")
            calls = [c[0][0] for c in mock_warn.call_args_list]
            assert any("SLACK_BOT_TOKEN" in msg for msg in calls)

    def test_warns_when_channel_id_empty(self):
        with patch.object(_slack_client_mod.logger, "warning") as mock_warn:
            SlackClient(bot_token="xoxb-test", channel_id="")
            calls = [c[0][0] for c in mock_warn.call_args_list]
            assert any("SLACK_CHANNEL_ID" in msg for msg in calls)

    @pytest.mark.asyncio
    async def test_send_team_alert_success(self):
        client = SlackClient(bot_token="xoxb-test", channel_id="C123")
        mock_web = AsyncMock()
        mock_web.chat_postMessage.return_value = {"ok": True}
        client._web_client = mock_web

        result = await client.send_team_alert(
            [{"type": "header", "text": {"type": "plain_text", "text": "test"}}],
            "test fallback",
        )
        assert result is True
        mock_web.chat_postMessage.assert_called_once_with(
            channel="C123",
            text="test fallback",
            blocks=[{"type": "header", "text": {"type": "plain_text", "text": "test"}}],
        )

    @pytest.mark.asyncio
    async def test_send_team_alert_retries_on_failure(self):
        client = SlackClient(bot_token="xoxb-test", channel_id="C123")
        mock_web = AsyncMock()
        mock_web.chat_postMessage.side_effect = [ConnectionError("fail"), {"ok": True}]
        client._web_client = mock_web

        with patch.object(_slack_client_mod.asyncio, "sleep", new_callable=AsyncMock) as mock_sleep:
            result = await client.send_team_alert([], "text")
            assert result is True
            assert mock_web.chat_postMessage.call_count == 2
            mock_sleep.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_send_team_alert_fails_after_max_retries(self):
        client = SlackClient(bot_token="xoxb-test", channel_id="C123")
        mock_web = AsyncMock()
        mock_web.chat_postMessage.side_effect = Exception("fail")
        client._web_client = mock_web

        with patch.object(_slack_client_mod.asyncio, "sleep", new_callable=AsyncMock):
            result = await client.send_team_alert([], "text")
            assert result is False
            assert mock_web.chat_postMessage.call_count == 2

    @pytest.mark.asyncio
    async def test_send_team_alert_retries_on_exception(self):
        client = SlackClient(bot_token="xoxb-test", channel_id="C123")
        mock_web = AsyncMock()
        mock_web.chat_postMessage.side_effect = [ConnectionError("unreachable"), {"ok": True}]
        client._web_client = mock_web

        with patch.object(_slack_client_mod.asyncio, "sleep", new_callable=AsyncMock) as mock_sleep:
            result = await client.send_team_alert([], "text")
            assert result is True
            mock_sleep.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_send_team_alert_exception_both_attempts_returns_false(self):
        client = SlackClient(bot_token="xoxb-test", channel_id="C123")
        mock_web = AsyncMock()
        mock_web.chat_postMessage.side_effect = ConnectionError("unreachable")
        client._web_client = mock_web

        with patch.object(_slack_client_mod.asyncio, "sleep", new_callable=AsyncMock):
            result = await client.send_team_alert([], "text")
            assert result is False

    @pytest.mark.asyncio
    async def test_send_team_alert_fails_when_no_bot_token(self):
        client = SlackClient(bot_token="", channel_id="C123")
        result = await client.send_team_alert([], "text")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_team_alert_fails_when_no_channel_id(self):
        client = SlackClient(bot_token="xoxb-test", channel_id="")
        result = await client.send_team_alert([], "text")
        assert result is False


# ---------------------------------------------------------------------------
# handle_team_alert integration tests
# ---------------------------------------------------------------------------

class TestHandleTeamAlert:
    @pytest.mark.asyncio
    async def test_sends_blocks_to_slack(self):
        n = Notification(**_team_alert_payload())
        mock_notifier = AsyncMock(return_value=True)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_team_alert = mock_notifier
            await handle_team_alert(n, "evt-100")

            mock_notifier.assert_called_once()
            blocks, fallback = mock_notifier.call_args[0]
            assert len(blocks) == 4  # header, fields, root_cause, actions
            assert "🔴 [P1] Ordering:" in fallback
    @pytest.mark.asyncio
    async def test_passes_event_id_to_adapter(self):
        n = Notification(**_team_alert_payload())
        mock_notifier = AsyncMock(return_value=True)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_team_alert = mock_notifier
            await handle_team_alert(n, "evt-corr-456")

            assert mock_notifier.call_args[1]["event_id"] == "evt-corr-456"
    @pytest.mark.asyncio
    async def test_logs_success(self):
        n = Notification(**_team_alert_payload())
        mock_notifier = AsyncMock(return_value=True)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_team_alert = mock_notifier
            with patch.object(_services.logger, "info") as mock_log:
                await handle_team_alert(n, "evt-100")
                log_messages = [c[0][0] for c in mock_log.call_args_list]
                assert any("Team alert sent" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_logs_failure_does_not_crash(self):
        n = Notification(**_team_alert_payload())
        mock_notifier = AsyncMock(return_value=False)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_team_alert = mock_notifier
            with patch.object(_services.logger, "error") as mock_log:
                await handle_team_alert(n, "evt-100")
                mock_log.assert_called_once()
                assert "Failed to send" in mock_log.call_args[0][0]

    @pytest.mark.asyncio
    async def test_event_id_in_log_messages(self):
        n = Notification(**_team_alert_payload())
        mock_notifier = AsyncMock(return_value=True)

        with patch.object(_services, "_slack_client") as mock_client:
            mock_client.send_team_alert = mock_notifier
            with patch.object(_services.logger, "info") as mock_log:
                await handle_team_alert(n, "evt-corr-123")
                log_calls = mock_log.call_args_list
                assert any("evt-corr-123" in str(c) for c in log_calls)


# ---------------------------------------------------------------------------
# Port interface compliance
# ---------------------------------------------------------------------------

class TestTeamNotifierPort:
    def test_port_is_abstract(self):
        with pytest.raises(TypeError):
            TeamNotifier()

    def test_send_team_alert_is_abstract_method(self):
        assert hasattr(TeamNotifier, "send_team_alert")
        assert getattr(TeamNotifier.send_team_alert, "__isabstractmethod__", False)
