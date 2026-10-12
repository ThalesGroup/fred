## ADDED Requirements

### Requirement: Local Vite startup loads the deployment theme ZIP

The local Vite frontend SHALL load an optional ZIP from `FRONTEND_THEME_URL` before serving application content. It SHALL honor the existing S3 credential, region and required-theme settings, apply the same archive validation and served-file allowlist as Docker, and fall back to stock files for omitted assets. Environment values SHALL override local configuration file values.

#### Scenario: Local task activates a SeaweedFS ZIP

- **WHEN** the frontend task starts with a valid SeaweedFS theme URL in `apps/frontend/config/.env`
- **THEN** its CSS, catalog, branding, images, fonts and translations are served before the application loads

#### Scenario: Private archive

- **WHEN** both S3 credentials are configured
- **THEN** the ZIP request is signed and credentials are absent from browser assets and logs

#### Scenario: Explicit environment wins

- **WHEN** the shell supplies a theme URL different from the local configuration file
- **THEN** Vite loads the shell-supplied URL

#### Scenario: Optional unavailable or invalid archive

- **WHEN** an optional ZIP cannot be fetched or fails the existing validation
- **THEN** Vite warns and serves stock files without a partial or stale overlay

#### Scenario: Required invalid archive

- **WHEN** theme loading fails with `FRONTEND_THEME_REQUIRED=true`
- **THEN** Vite refuses to start

### Requirement: Local theme overlays preserve the checkout

Local theme loading SHALL preserve tracked public files, limit requests to the existing supported theme surfaces, and fetch replacement ZIPs only on server restart. Unsetting the theme URL SHALL restore stock behavior on the next startup.

#### Scenario: Replace and restart

- **WHEN** the storage ZIP is replaced and Vite is restarted
- **THEN** a refreshed browser receives the replacement theme without changes to tracked public files

#### Scenario: Protected bundle and paths

- **WHEN** the archive includes `index.html`, `config.json`, bundle files, escaping paths or symlinks
- **THEN** the existing validation rejects escaping archives and unsupported files are not served as theme overrides

#### Scenario: Disable local overlay

- **WHEN** Vite starts without a theme URL after a previously themed run
- **THEN** it serves stock assets without the previous overlay
