# Story 2.3: UI-API Form Submission Integration

> **Epic:** 2 — Incident Submission Experience (UI + API)
> **Status:** done
> **Priority:** 🟠 High — UI path priority workstream
> **Depends on:** Story 2.1 (UI deployed), Story 2.2 (API endpoint live)
> **FRs:** FR1, FR2, FR3, FR4, FR6

## Story

**As a** reporter,
**I want** to fill out the incident form and submit it, then see a confirmation screen with my tracking ID,
**So that** I know Mila received my report and is processing it.

## Acceptance Criteria

**Given** the reporter has filled in the title field (at minimum)
**When** the reporter clicks the Submit button
**Then** the form sends a POST request to `/api/incidents` with all form data (title, description, component, severity, file)
**And** the severity value from the button selection is captured and sent (the HTML needs a hidden input or JS capture for the active severity button)
**And** the file attachment is sent as multipart form data

**Given** the API returns HTTP 201 with an `incident_id`
**When** the UI processes the response
**Then** the success screen displays with the `incident_id` as the tracking reference (replacing the current random client-side number)
**And** the "Mila is on it" message and "What happens next" steps are shown

**Given** the API returns an error (4xx or 5xx)
**When** the UI processes the error response
**Then** the reporter sees a user-friendly error message (not a raw API error)
**And** the form remains filled so the reporter can retry

## Tasks / Subtasks

- [x] **1. Capture severity button value**
  - The current HTML uses CSS-only severity buttons with no value capture
  - Add JS to track which severity button is active and store the value
  - Options: add a hidden input field, or track via JS variable

- [x] **2. Modify submitForm() to make API call**
  - Replace the current client-side-only `submitForm()` with an actual `fetch()` call
  - POST to `/api/incidents` (relative path — nginx proxies to API)
  - Build `FormData` with: title, description, component, severity, file
  - Set appropriate headers for multipart/form-data

- [x] **3. Handle success response**
  - Parse API response `{ status: "ok", data: { incident_id } }`
  - Replace the random ticket ID in the success screen with `incident_id`
  - Show the "Mila is on it" success state

- [x] **4. Handle error response**
  - Show user-friendly error message on 4xx (e.g., "Title is required")
  - Show generic retry message on 5xx (e.g., "Something went wrong. Please try again.")
  - Keep form data filled so reporter can retry without re-entering

- [x] **5. Add loading state**
  - Show a spinner or "Submitting..." state while the API call is in flight
  - Disable the submit button to prevent double-submission

## Dev Notes

### Architecture Guardrails
- **Static SPA:** All JS is inline in the HTML — no build step, no framework.
- **Relative API path:** Use `/api/incidents` — nginx handles the proxy. No hardcoded backend URLs.
- **No email/Resend:** Reporter identity is server-side (config). The form does NOT collect email.

### Current UI State (from analysis)
- `submitForm()` function exists but only does client-side validation and shows a hardcoded success screen
- Severity buttons are CSS-only — clicking them changes visual state but no value is captured in JS
- File upload preview works client-side but the file is not sent to any API
- Success screen shows a random ticket ID like `INC-1234567` — needs to be replaced with real `incident_id`

### Fetch Pattern
```javascript
async function submitForm() {
  const formData = new FormData();
  formData.append('title', document.getElementById('title').value);
  formData.append('description', document.getElementById('description').value);
  formData.append('component', document.getElementById('component').value);
  formData.append('severity', selectedSeverity); // captured from button click
  if (fileInput.files[0]) {
    formData.append('file', fileInput.files[0]);
  }

  try {
    const response = await fetch('/api/incidents', { method: 'POST', body: formData });
    const data = await response.json();
    if (response.ok) {
      showSuccess(data.data.incident_id);
    } else {
      showError(data.message);
    }
  } catch (err) {
    showError('Something went wrong. Please try again.');
  }
}
```

### Key Reference Files
- UI file: `services/ui/public/index.html` (deployed in Story 2.1)
- API endpoint: Story 2.2 (`POST /api/incidents`)
- Original UI: `docs/mila_ui_final_v1.html`

## Chat Command Log

### Implementation Notes (2026-04-08)

**Decision: JS variable for severity** — Used a global `selectedSeverity` variable with a `values` array mapping (`['low','medium','high','critical']`) indexed by button position. Simpler than a hidden input and avoids DOM queries on submit.

**Decision: client-side title validation** — Added a pre-flight title check in `submitForm()` before calling `fetch()` to provide instant feedback without a round-trip. The API also validates server-side (defense in depth).

**Decision: no Content-Type header** — FormData with `fetch()` auto-sets the correct `multipart/form-data` boundary. Manually setting `Content-Type` would break file uploads.

**Decision: loading state via opacity** — Used `btn.style.opacity = '0.6'` + `btn.disabled = true` for loading UX. Separate `<span>` elements for text/arrow/spinner are toggled via `display`, avoiding innerHTML manipulation.

**Decision: error display element** — Added a `#form-error` div with styled error banner above the form footer. Hidden by default, shown via `showError()` / hidden via `hideError()`. The form remains visible on error so the reporter can fix and retry.

**Decision: removed MILA- prefix from ticket-id** — The API returns a UUID `incident_id`, not a sequential number. The success screen now shows the raw UUID from `data.data.incident_id`.

### File List
- `services/ui/public/index.html` — All 5 tasks implemented (severity capture, API fetch, success/error/loading states)
- `tests/test_ui_api_integration.py` — 45 new tests (severity, API call, success, error, loading, regression)

### Change Log
- 2026-04-08: Implemented all 5 tasks for Story 2.3. 45 new tests, 127 total tests pass (0 regressions; 14 pre-existing failures in agent scaffold unrelated to this story).
- 2026-04-08: Code review — 1 patch fixed (progress bar reset on error), 3 deferred (fetch timeout, client file-size validation, aria-live), 15 dismissed. 46 tests now (1 new for fix). Status → done.

### Review Findings
- [x] [Review][Patch] Progress bar stuck at 90% on error — added `updateProgress()` calls in both error paths [index.html]
- [x] [Review][Defer] No fetch timeout on API call — deferred, enhancement beyond story scope
- [x] [Review][Defer] No client-side file size validation (50MB limit) — deferred, API validates server-side (Story 2.2)
- [x] [Review][Defer] No aria-live region for error announcements — deferred, accessibility improvement beyond story scope
