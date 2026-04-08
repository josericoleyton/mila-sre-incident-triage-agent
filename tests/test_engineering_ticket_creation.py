"""
Tests for Engineering Ticket Creation (Story 4.2).

Covers:
- LinearClient adapter: create_issue, retry logic, backoff
- Domain services: create_engineering_ticket full flow
- Severity-to-priority mapping
- Team notification publishing after success
- Reporter notification publishing (when reporter_slack_user_id present)
- No reporter notification when reporter_slack_user_id is None
- Ticket-incident mapping publication
- Error handling: Linear API failure → ticket.error, no notifications
- handle_ticket_command integration with ticket_creator

Run:
    pytest tests/test_engineering_ticket_creation.py -v
"""

import importlib.util
import json
import sys
import types as _types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx as _httpx
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TS_ROOT = _PROJECT_ROOT / "services" / "ticket-service"


# ---------------------------------------------------------------------------
# Module loading helpers (same pattern as test_ticket_service_scaffold.py)
# ---------------------------------------------------------------------------
from contextlib import contextmanager


def _load_module_raw(name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@contextmanager
def _ticket_service_context():
    saved = dict(sys.modules)
    saved_path = list(sys.path)

    svc_path = str(_TS_ROOT)
    if svc_path in sys.path:
        sys.path.remove(svc_path)
    sys.path.insert(0, svc_path)

    src_pkg = _types.ModuleType("src")
    src_pkg.__path__ = [str(_TS_ROOT / "src")]
    src_pkg.__package__ = "src"
    sys.modules["src"] = src_pkg

    domain_pkg = _types.ModuleType("src.domain")
    domain_pkg.__path__ = [str(_TS_ROOT / "src" / "domain")]
    domain_pkg.__package__ = "src.domain"
    sys.modules["src.domain"] = domain_pkg

    ports_pkg = _types.ModuleType("src.ports")
    ports_pkg.__path__ = [str(_TS_ROOT / "src" / "ports")]
    sys.modules["src.ports"] = ports_pkg

    adapters_pkg = _types.ModuleType("src.adapters")
    adapters_pkg.__path__ = [str(_TS_ROOT / "src" / "adapters")]
    sys.modules["src.adapters"] = adapters_pkg

    adapters_inbound_pkg = _types.ModuleType("src.adapters.inbound")
    adapters_inbound_pkg.__path__ = [str(_TS_ROOT / "src" / "adapters" / "inbound")]
    sys.modules["src.adapters.inbound"] = adapters_inbound_pkg

    adapters_outbound_pkg = _types.ModuleType("src.adapters.outbound")
    adapters_outbound_pkg.__path__ = [str(_TS_ROOT / "src" / "adapters" / "outbound")]
    sys.modules["src.adapters.outbound"] = adapters_outbound_pkg

    _load_module_raw("src.config", _TS_ROOT / "src" / "config.py")
    _load_module_raw("src.ports.inbound", _TS_ROOT / "src" / "ports" / "inbound.py")
    _load_module_raw("src.ports.outbound", _TS_ROOT / "src" / "ports" / "outbound.py")
    _load_module_raw("src.domain.models", _TS_ROOT / "src" / "domain" / "models.py")
    _load_module_raw("src.domain.services", _TS_ROOT / "src" / "domain" / "services.py")
    _load_module_raw("src.adapters.inbound.redis_consumer", _TS_ROOT / "src" / "adapters" / "inbound" / "redis_consumer.py")
    _load_module_raw("src.adapters.inbound.webhook_listener", _TS_ROOT / "src" / "adapters" / "inbound" / "webhook_listener.py")
    _load_module_raw("src.adapters.outbound.redis_publisher", _TS_ROOT / "src" / "adapters" / "outbound" / "redis_publisher.py")
    _load_module_raw("src.adapters.outbound.linear_client", _TS_ROOT / "src" / "adapters" / "outbound" / "linear_client.py")

    try:
        yield
    finally:
        new_keys = set(sys.modules.keys()) - set(saved.keys())
        for k in new_keys:
            del sys.modules[k]
        sys.modules.update(saved)
        sys.path[:] = saved_path


with _ticket_service_context():
    _models = sys.modules["src.domain.models"]
    _services = sys.modules["src.domain.services"]
    _linear_client_mod = sys.modules["src.adapters.outbound.linear_client"]

TicketCommand = _models.TicketCommand
TicketResult = _models.TicketResult
create_engineering_ticket = _services.create_engineering_ticket
handle_ticket_command = _services.handle_ticket_command
_map_severity_to_priority = _services._map_severity_to_priority
LinearClient = _linear_client_mod.LinearClient


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


def _valid_ticket_command_payload(**overrides) -> dict:
    base = {
        "action": "create_engineering_ticket",
        "title": "[P2] NullReferenceException in OrderController.cs",
        "body": "## Affected Files\n- OrderController.cs:42\n\n## Root Cause\nNull ref on order lookup",
        "severity": "P2",
        "labels": ["ordering", "triaged-by-mila"],
        "reporter_slack_user_id": "U12345",
        "incident_id": "inc-200",
    }
    base.update(overrides)
    return base


def _mock_linear_issue(**overrides) -> dict:
    base = {
        "id": "issue-uuid-123",
        "identifier": "ENG-42",
        "url": "https://linear.app/team/issue/ENG-42",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Severity-to-priority mapping tests
# ---------------------------------------------------------------------------

class TestSeverityToPriorityMapping:
    def test_p1_maps_to_urgent(self):
        assert _map_severity_to_priority("P1") == 1

    def test_p2_maps_to_high(self):
        assert _map_severity_to_priority("P2") == 2

    def test_p3_maps_to_medium(self):
        assert _map_severity_to_priority("P3") == 3

    def test_p4_maps_to_low(self):
        assert _map_severity_to_priority("P4") == 4

    def test_lowercase_severity(self):
        assert _map_severity_to_priority("p1") == 1

    def test_severity_with_whitespace(self):
        assert _map_severity_to_priority("  P2  ") == 2

    def test_unknown_severity_defaults_to_medium(self):
        assert _map_severity_to_priority("critical") == 3

    def test_severity_embedded_in_string(self):
        assert _map_severity_to_priority("severity-P1-critical") == 1

    def test_p12_does_not_match_p1(self):
        """Digit after severity key should not match (P12 ≠ P1)."""
        assert _map_severity_to_priority("P12") == 3


# ---------------------------------------------------------------------------
# create_engineering_ticket domain logic tests
# ---------------------------------------------------------------------------

class TestCreateEngineeringTicket:
    @pytest.mark.asyncio
    async def test_success_creates_ticket_and_returns_result(self):
        command = TicketCommand(**_valid_ticket_command_payload())
        ticket_creator = AsyncMock()
        ticket_creator.create_issue.return_value = _mock_linear_issue()
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        result = await create_engineering_ticket(command, ticket_creator, publisher, "evt-abc")

        assert result is not None
        assert result.ticket_id == "issue-uuid-123"
        assert result.identifier == "ENG-42"
        assert result.url == "https://linear.app/team/issue/ENG-42"
        assert result.incident_id == "inc-200"

    @pytest.mark.asyncio
    async def test_calls_linear_with_correct_priority(self):
        command = TicketCommand(**_valid_ticket_command_payload(severity="P1"))
        ticket_creator = AsyncMock()
        ticket_creator.create_issue.return_value = _mock_linear_issue()
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        await create_engineering_ticket(command, ticket_creator, publisher, "evt-abc")

        _, kwargs = ticket_creator.create_issue.call_args
        assert kwargs["priority"] == 1

    @pytest.mark.asyncio
    async def test_publishes_team_notification_on_success(self):
        command = TicketCommand(**_valid_ticket_command_payload())
        ticket_creator = AsyncMock()
        ticket_creator.create_issue.return_value = _mock_linear_issue()
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        await create_engineering_ticket(command, ticket_creator, publisher, "evt-abc")

        # Find the team_alert publish call
        calls = publisher.publish.call_args_list
        team_alert_calls = [c for c in calls if c[0][0] == "notifications" and c[0][2].get("type") == "team_alert"]
        assert len(team_alert_calls) == 1
        payload = team_alert_calls[0][0][2]
        assert payload["ticket_url"] == "https://linear.app/team/issue/ENG-42"
        assert payload["severity"] == "P2"
        assert payload["component"] == "ordering"
        assert payload["summary"] == "[P2] NullReferenceException in OrderController.cs"
        assert payload["incident_id"] == "inc-200"

    @pytest.mark.asyncio
    async def test_publishes_reporter_notification_when_reporter_exists(self):
        command = TicketCommand(**_valid_ticket_command_payload(reporter_slack_user_id="U99999"))
        ticket_creator = AsyncMock()
        ticket_creator.create_issue.return_value = _mock_linear_issue()
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        await create_engineering_ticket(command, ticket_creator, publisher, "evt-abc")

        calls = publisher.publish.call_args_list
        reporter_calls = [c for c in calls if c[0][0] == "notifications" and c[0][2].get("type") == "reporter_update"]
        assert len(reporter_calls) == 1
        payload = reporter_calls[0][0][2]
        assert payload["slack_user_id"] == "U99999"
        assert "inc-200" in payload["message"]
        assert "escalated" in payload["message"]

    @pytest.mark.asyncio
    async def test_no_reporter_notification_when_reporter_is_none(self):
        command = TicketCommand(**_valid_ticket_command_payload(reporter_slack_user_id=None))
        ticket_creator = AsyncMock()
        ticket_creator.create_issue.return_value = _mock_linear_issue()
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        await create_engineering_ticket(command, ticket_creator, publisher, "evt-abc")

        calls = publisher.publish.call_args_list
        reporter_calls = [c for c in calls if c[0][0] == "notifications" and c[0][2].get("type") == "reporter_update"]
        assert len(reporter_calls) == 0

    @pytest.mark.asyncio
    async def test_no_ticket_mapping_pubsub_publish(self):
        """ticket-mappings PubSub removed in Story 4.3 — mapping uses Redis hash store now."""
        command = TicketCommand(**_valid_ticket_command_payload())
        ticket_creator = AsyncMock()
        ticket_creator.create_issue.return_value = _mock_linear_issue()
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        await create_engineering_ticket(command, ticket_creator, publisher, "evt-abc")

        calls = publisher.publish.call_args_list
        mapping_calls = [c for c in calls if c[0][0] == "ticket-mappings"]
        assert len(mapping_calls) == 0

    @pytest.mark.asyncio
    async def test_linear_failure_publishes_error_no_notifications(self):
        command = TicketCommand(**_valid_ticket_command_payload())
        ticket_creator = AsyncMock()
        ticket_creator.create_issue.side_effect = RuntimeError("Linear API timeout")
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        result = await create_engineering_ticket(command, ticket_creator, publisher, "evt-abc")

        assert result is None
        # Should publish ticket.error to errors channel
        calls = publisher.publish.call_args_list
        error_calls = [c for c in calls if c[0][0] == "errors"]
        assert len(error_calls) == 1
        assert error_calls[0][0][1] == "ticket.error"
        # Should NOT publish any notifications
        notification_calls = [c for c in calls if c[0][0] == "notifications"]
        assert len(notification_calls) == 0

    @pytest.mark.asyncio
    async def test_empty_labels_uses_unknown_component(self):
        command = TicketCommand(**_valid_ticket_command_payload(labels=[]))
        ticket_creator = AsyncMock()
        ticket_creator.create_issue.return_value = _mock_linear_issue()
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        await create_engineering_ticket(command, ticket_creator, publisher, "evt-abc")

        calls = publisher.publish.call_args_list
        team_alert_calls = [c for c in calls if c[0][0] == "notifications" and c[0][2].get("type") == "team_alert"]
        assert team_alert_calls[0][0][2]["component"] == "unknown"

    @pytest.mark.asyncio
    async def test_notification_failure_still_returns_result(self):
        """If notification publish fails, TicketResult is still returned (fix #1)."""
        command = TicketCommand(**_valid_ticket_command_payload())
        ticket_creator = AsyncMock()
        ticket_creator.create_issue.return_value = _mock_linear_issue()
        publisher = AsyncMock()

        call_count = 0

        async def _publish_side_effect(channel, event_type, payload):
            nonlocal call_count
            call_count += 1
            if channel == "notifications":
                raise ConnectionError("Redis down")
            return "evt-1"

        publisher.publish.side_effect = _publish_side_effect

        result = await create_engineering_ticket(command, ticket_creator, publisher, "evt-abc")

        assert result is not None
        assert result.identifier == "ENG-42"


# ---------------------------------------------------------------------------
# LinearClient adapter tests
# ---------------------------------------------------------------------------

class TestLinearClient:
    @pytest.mark.asyncio
    async def test_create_issue_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": _mock_linear_issue(),
                }
            }
        }
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response

        client = LinearClient(http_client=mock_http)
        result = await client.create_issue(
            title="Test",
            body="Body",
            priority=2,
            labels=["label1"],
            team_id="team-123",
        )

        assert result["identifier"] == "ENG-42"
        assert result["url"] == "https://linear.app/team/issue/ENG-42"
        mock_http.post.assert_called_once()

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_create_issue_retries_on_http_error(self, mock_sleep):
        fail_response = MagicMock()
        fail_response.status_code = 500
        fail_response.raise_for_status.side_effect = _httpx.HTTPStatusError(
            "500", request=MagicMock(), response=fail_response,
        )

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.raise_for_status = MagicMock()
        success_response.json.return_value = {
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": _mock_linear_issue(),
                }
            }
        }

        mock_http = AsyncMock()
        mock_http.post.side_effect = [fail_response, success_response]

        client = LinearClient(http_client=mock_http)
        result = await client.create_issue(
            title="Test",
            body="Body",
            priority=2,
            labels=[],
            team_id="team-123",
        )

        assert result["identifier"] == "ENG-42"
        assert mock_http.post.call_count == 2
        mock_sleep.assert_called_once_with(1)

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_create_issue_raises_after_max_retries(self, mock_sleep):
        fail_response = MagicMock()
        fail_response.status_code = 500
        fail_response.raise_for_status.side_effect = _httpx.HTTPStatusError(
            "500", request=MagicMock(), response=fail_response,
        )

        mock_http = AsyncMock()
        mock_http.post.return_value = fail_response

        client = LinearClient(http_client=mock_http)
        with pytest.raises(_httpx.HTTPStatusError):
            await client.create_issue(
                title="Test",
                body="Body",
                priority=2,
                labels=[],
                team_id="team-123",
            )

        # 3 total attempts (1 + 2 retries)
        assert mock_http.post.call_count == 3
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_create_issue_raises_on_success_false(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "issueCreate": {
                    "success": False,
                }
            },
            "errors": [{"message": "Invalid input"}],
        }

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response

        client = LinearClient(http_client=mock_http)
        with pytest.raises(RuntimeError, match="success=false"):
            await client.create_issue(
                title="Test",
                body="Body",
                priority=2,
                labels=[],
                team_id="team-123",
            )

        # Deterministic failure — no retries
        assert mock_http.post.call_count == 1


# ---------------------------------------------------------------------------
# handle_ticket_command integration with ticket_creator
# ---------------------------------------------------------------------------

class TestHandleTicketCommandWithCreator:
    @pytest.mark.asyncio
    async def test_routes_to_create_engineering_ticket(self):
        envelope = _build_envelope("ticket.create", "agent", _valid_ticket_command_payload())
        ticket_creator = AsyncMock()
        ticket_creator.create_issue.return_value = _mock_linear_issue()
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        result = await handle_ticket_command(envelope, publisher, ticket_creator=ticket_creator)

        assert result is not None
        assert result.action == "create_engineering_ticket"
        ticket_creator.create_issue.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_ticket_creator_publishes_error(self):
        envelope = _build_envelope("ticket.create", "agent", _valid_ticket_command_payload())
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        result = await handle_ticket_command(envelope, publisher, ticket_creator=None)

        assert result is None
        publisher.publish.assert_called_once()
        call_args = publisher.publish.call_args
        assert call_args[0][0] == "errors"
        assert "not configured" in call_args[0][2]["error"]

    @pytest.mark.asyncio
    async def test_backward_compat_unrecognized_action(self):
        envelope = _build_envelope(
            "ticket.create", "agent", _valid_ticket_command_payload(action="unknown"),
        )
        publisher = AsyncMock()

        result = await handle_ticket_command(envelope, publisher)

        assert result is None
        publisher.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_backward_compat_malformed_payload(self):
        envelope = _build_envelope("ticket.create", "agent", {"action": "create_engineering_ticket"})
        publisher = AsyncMock()
        publisher.publish.return_value = "evt-1"

        result = await handle_ticket_command(envelope, publisher)

        assert result is None
        publisher.publish.assert_called_once()
        assert publisher.publish.call_args[0][1] == "ticket.error"
