## MODIFIED Requirements

### Requirement: Administrators manage independent Free-link history

Only platform administrators SHALL create, list and revoke Free-team links. The platform administration Teams registry SHALL expose the Free toggle and Manage links action for each eligible team; ordinary team managers SHALL NOT see these controls or issue admission administration queries. Platform access SHALL group individual exceptions and independent team authorization in its Whitelist panel and SHALL NOT duplicate Free/link controls. The bounded paginated history SHALL expose the link identifier, note, creation and expiry dates, revocation state, suspension state and authenticated opening count, without reusable tokens or visitor identity. Administrators SHALL be able to inspect and revoke links while Free is disabled. Manage links SHALL open on the bounded invitation list with a Create link action; note and expiry inputs SHALL appear only in a separate creation view. That view SHALL place the optional note before optional expiration and reuse the platform KPI selector presentation, with a single future date/time input, future duration shortcuts, a No expiration option and Apply. The date draft SHALL prevent creation until applied or dismissed; Escape SHALL close only the selector and restore trigger focus. Empty expiration SHALL mean no expiry; invalid or past expiration SHALL prevent creation without losing the note. Generation success SHALL show the original URL in the platform's monospace font and an immediately available Copy URL action, and SHALL attempt to copy that URL to the clipboard automatically.

History SHALL use an explicit Copy URL action that recovers the original token and attempts clipboard writing without generating another link. Clipboard success SHALL be announced only after the write succeeds through temporary feedback on the corresponding Copy URL button and a screen-reader status, without changing the dialog layout. If clipboard writing is unavailable or rejected, the UI SHALL retain the usable URL with a clear manual-copy fallback; a copy failure SHALL NOT be presented as generation failure or cause another invitation to be created. Creation/recovery URL state SHALL remain transient and clear on manager dismissal, without logging URLs or retaining reusable mutation payloads.

The opening-count column SHALL use the short localized label Accesses (Accès) without showing the last-access timestamp, and explain that it counts authenticated page openings rather than unique users, anonymous clicks or message delivery. The UI SHALL identify manual sharing and explicit URL recovery; it SHALL NOT claim message delivery.

#### Scenario: Generate a second invitation

- **WHEN** an administrator creates another link with a note and optional future expiry
- **THEN** both invitations SHALL remain independently usable until their own revocation or expiry
- **AND** their purposes, lifecycle and opening counts SHALL appear in history

#### Scenario: Ordinary team manager attempts link administration

- **WHEN** a person without platform-management authority calls link administration
- **THEN** no link history, reusable token or mutation SHALL be granted

#### Scenario: Copy a previously generated invitation

- **WHEN** an own-human platform administrator requests a usable invitation URL from history
- **THEN** the original token SHALL be returned without changing its validity or opening count
- **AND** ordinary listing and workload/delegated requests SHALL NOT expose that token

#### Scenario: Revoke one invitation

- **WHEN** one invitation is revoked
- **THEN** other valid invitations SHALL remain usable and existing team membership SHALL remain intact

#### Scenario: Open history without a creation form

- **WHEN** an administrator opens Manage links
- **THEN** the invitation list and Create link action SHALL appear without note or expiration inputs
- **WHEN** the administrator chooses Create link
- **THEN** a separate creation form SHALL appear with note followed by expiration

#### Scenario: Cancel creation

- **WHEN** the administrator cancels the creation form
- **THEN** the history SHALL remain available and no invitation SHALL be generated

#### Scenario: Created invitation is ready to copy

- **WHEN** generation succeeds
- **THEN** the usable invitation URL and Copy URL action SHALL be shown with successful creation feedback
- **AND** the displayed URL SHALL use the platform's monospace font
- **AND** the UI SHALL attempt to copy that URL to the clipboard automatically
- **AND** clipboard success SHALL be announced only after the write succeeds; creation SHALL NOT claim message delivery

#### Scenario: Copy from invitation history

- **WHEN** an own-human platform administrator chooses Copy URL on a recoverable row
- **THEN** the existing original URL SHALL be recovered and written to the clipboard
- **AND** successful copy feedback SHALL appear only after clipboard confirmation, without changing link validity or counts

#### Scenario: Clipboard access is refused

- **WHEN** the browser refuses clipboard access after generation or recovery
- **THEN** the usable URL SHALL remain available for manual copying with specific feedback
- **AND** no replacement invitation SHALL be created and the failure SHALL NOT be announced as a failed creation

#### Scenario: Delayed clipboard result after dismissal

- **WHEN** an administrator dismisses the generated URL or begins a newer copy while a clipboard write is pending
- **THEN** a later result from the earlier write SHALL NOT reopen the dismissed dialog or replace the newer copy feedback

#### Scenario: Short counter heading retains its meaning

- **WHEN** the invitation history displays Accesses
- **THEN** the displayed value SHALL remain the authenticated opening aggregate and the counting definition SHALL remain available

#### Scenario: Invalid creation input retains the draft

- **WHEN** expiration is invalid or no longer in the future, or generation fails
- **THEN** the creation form SHALL retain the note and date with actionable feedback, without closing the manager
