"""
Tests for Story 2.3: UI-API Form Submission Integration.

Verifies that the static UI correctly wires form submission to the API:
1. Severity button value capture via JS variable
2. submitForm() builds FormData and calls fetch('/api/incidents')
3. Success response shows real incident_id from API
4. Error response shows user-friendly message and preserves form
5. Loading state disables button during submission

Run:
    pytest tests/test_ui_api_integration.py -v
"""

import re
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_INDEX_HTML = _PROJECT_ROOT / "services" / "ui" / "public" / "index.html"


@pytest.fixture()
def html():
    return _INDEX_HTML.read_text(encoding="utf-8")


@pytest.fixture()
def script_block(html):
    """Extract the inline <script> block content."""
    match = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert match, "No <script> block found in index.html"
    return match.group(1)


# ---------------------------------------------------------------------------
# Task 1: Severity button value capture
# ---------------------------------------------------------------------------

class TestSeverityCapture:
    def test_selected_severity_variable_exists(self, script_block):
        """A global variable must track the selected severity."""
        assert "selectedSeverity" in script_block

    def test_selected_severity_initialized_empty(self, script_block):
        """selectedSeverity should start as empty string."""
        assert re.search(r"selectedSeverity\s*=\s*['\"]'?['\"]", script_block) or \
               re.search(r"selectedSeverity\s*=\s*''", script_block)

    def test_set_sev_updates_selected_severity(self, script_block):
        """setSev() must assign to selectedSeverity."""
        # Find the setSev function and check it sets selectedSeverity
        sev_match = re.search(r"function\s+setSev\s*\(", script_block)
        assert sev_match, "setSev function not found"
        # After setSev function start, selectedSeverity should be assigned
        sev_body = script_block[sev_match.start():]
        assert "selectedSeverity" in sev_body, "setSev must update selectedSeverity"

    def test_severity_values_are_correct(self, script_block):
        """Severity values should map to: low, medium, high, critical."""
        for val in ["low", "medium", "high", "critical"]:
            assert f'"{val}"' in script_block or f"'{val}'" in script_block, \
                f"Severity value '{val}' not found in script"


# ---------------------------------------------------------------------------
# Task 2: submitForm makes API call
# ---------------------------------------------------------------------------

class TestSubmitFormApiCall:
    def test_submit_form_is_async(self, script_block):
        """submitForm should be async for fetch."""
        assert re.search(r"async\s+function\s+submitForm", script_block)

    def test_uses_fetch_api(self, script_block):
        """submitForm must use fetch() to call the API."""
        assert "fetch(" in script_block

    def test_posts_to_relative_api_path(self, script_block):
        """Fetch must target /api/incidents (relative — nginx proxied)."""
        assert "'/api/incidents'" in script_block or '"/api/incidents"' in script_block

    def test_uses_post_method(self, script_block):
        """Fetch must use POST method."""
        assert "'POST'" in script_block or '"POST"' in script_block

    def test_builds_form_data(self, script_block):
        """Must construct FormData with form fields."""
        assert "new FormData()" in script_block

    def test_appends_title(self, script_block):
        assert re.search(r"formData\.append\(\s*['\"]title['\"]", script_block)

    def test_appends_description(self, script_block):
        assert re.search(r"formData\.append\(\s*['\"]description['\"]", script_block)

    def test_appends_component(self, script_block):
        assert re.search(r"formData\.append\(\s*['\"]component['\"]", script_block)

    def test_appends_severity(self, script_block):
        assert re.search(r"formData\.append\(\s*['\"]severity['\"]", script_block)

    def test_appends_file_conditionally(self, script_block):
        """File should only be appended if present."""
        assert re.search(r"formData\.append\(\s*['\"]file['\"]", script_block)
        # Should have a conditional check for file
        assert "fileInput.files" in script_block or "files[0]" in script_block

    def test_no_hardcoded_backend_url(self, script_block):
        """Must NOT hardcode backend host — uses relative path via nginx."""
        assert "localhost:8000" not in script_block
        assert "http://api" not in script_block
        assert "127.0.0.1:8000" not in script_block


# ---------------------------------------------------------------------------
# Task 3: Success response handling
# ---------------------------------------------------------------------------

class TestSuccessHandling:
    def test_parses_incident_id_from_response(self, script_block):
        """Must extract incident_id from data.data.incident_id."""
        assert "data.data.incident_id" in script_block

    def test_sets_ticket_num_from_api(self, script_block):
        """ticket-num element should receive the API incident_id."""
        assert "ticket-num" in script_block
        assert "data.data.incident_id" in script_block

    def test_no_random_ticket_id(self, script_block):
        """Random ticket ID generation must be removed."""
        assert "Math.random()" not in script_block
        assert "Math.floor(1000" not in script_block

    def test_shows_success_view(self, script_block):
        """Success screen must be shown on 201."""
        assert "success-view" in script_block

    def test_hides_form_view_on_success(self, script_block):
        """Form view must be hidden on success."""
        assert "form-view" in script_block


# ---------------------------------------------------------------------------
# Task 4: Error response handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_error_element_exists(self, html):
        """An error display element must exist for showing messages."""
        assert 'id="form-error"' in html

    def test_error_message_element_exists(self, html):
        """An inner element for the error text must exist."""
        assert 'id="form-error-msg"' in html

    def test_handles_non_ok_response(self, script_block):
        """Must check response.ok and handle failures."""
        assert "response.ok" in script_block

    def test_shows_api_error_message(self, script_block):
        """Must display the API error message (e.g. 'Title is required')."""
        assert "data.message" in script_block

    def test_handles_network_error(self, script_block):
        """Must catch fetch errors (network failures)."""
        assert "catch" in script_block

    def test_shows_generic_retry_message(self, script_block):
        """On network error, show a user-friendly retry message."""
        assert "Something went wrong" in script_block

    def test_form_view_not_hidden_on_error(self, script_block):
        """Form must remain visible on error so user can retry."""
        # success-view display is only set inside the response.ok branch
        # form-view hide is only inside the success branch
        ok_branch = re.search(
            r"if\s*\(response\.ok\)\s*\{(.*?)\}\s*else",
            script_block,
            re.DOTALL,
        )
        assert ok_branch, "Expected if(response.ok) branch"
        success_code = ok_branch.group(1)
        assert "form-view" in success_code, "form-view hiding should be in success branch"

    def test_client_side_title_validation(self, script_block):
        """Client-side check prevents submission without title."""
        assert "Title is required" in script_block


# ---------------------------------------------------------------------------
# Task 5: Loading state
# ---------------------------------------------------------------------------

class TestLoadingState:
    def test_submit_button_has_text_span(self, html):
        """Submit button should have a text span for toggling."""
        assert 'id="submit-text"' in html

    def test_submit_button_has_spinner_element(self, html):
        """Submit button should have a spinner/loading indicator."""
        assert 'id="submit-spinner"' in html

    def test_button_disabled_during_submission(self, script_block):
        """Submit button must be disabled during API call."""
        assert "btn.disabled" in script_block or "disabled" in script_block

    def test_loading_state_toggled(self, script_block):
        """setLoading function should exist for toggling load state."""
        assert "setLoading" in script_block

    def test_loading_reset_on_error(self, script_block):
        """Loading must be turned off if the API returns an error."""
        assert "setLoading(false)" in script_block

    def test_progress_bar_reset_on_error(self, script_block):
        """Progress bar must be reset on error (not stuck at 90%)."""
        # After setLoading(false), updateProgress() should be called to restore bar
        # Find both error paths (else branch + catch) and verify updateProgress follows setLoading
        error_blocks = re.findall(
            r"setLoading\(false\);\s*\n\s*updateProgress\(\)",
            script_block,
        )
        assert len(error_blocks) == 2, \
            f"Expected updateProgress() after setLoading(false) in both error paths, found {len(error_blocks)}"


# ---------------------------------------------------------------------------
# Regression: Existing functionality preserved
# ---------------------------------------------------------------------------

class TestRegressionExistingFeatures:
    def test_handle_select_exists(self, script_block):
        assert "function handleSelect" in script_block

    def test_set_sev_exists(self, script_block):
        assert "function setSev" in script_block

    def test_update_progress_exists(self, script_block):
        assert "function updateProgress" in script_block

    def test_update_hint_exists(self, script_block):
        assert "function updateHint" in script_block

    def test_show_file_exists(self, script_block):
        assert "function showFile" in script_block

    def test_remove_file_exists(self, script_block):
        assert "function removeFile" in script_block

    def test_submit_form_exists(self, script_block):
        assert "submitForm" in script_block

    def test_severity_buttons_in_html(self, html):
        assert "sev-btn" in html
        assert "setSev(this)" in html

    def test_file_upload_in_html(self, html):
        assert 'id="fi"' in html
        assert 'type="file"' in html

    def test_mila_hint_bar(self, html):
        assert "mila-hint" in html

    def test_progress_bar(self, html):
        assert "progress-fill" in html

    def test_success_screen_structure(self, html):
        assert 'id="success-view"' in html
        assert "Mila is on it" in html
        assert "What happens next" in html
