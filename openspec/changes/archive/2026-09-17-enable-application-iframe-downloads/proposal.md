## Why

An entitled hosted application can prepare a local file in its iframe, but FRED's current iframe sandbox omits download permission, so the browser can block the final download. The immediate consumer is the RAGS Information Systems application's user-triggered Markdown synthesis export; its child-side Blob and anchor flow already passes isolated checks, which cannot establish behavior in FRED's sandboxed host.

## What Changes

- Permit browser-native local downloads from an admitted application iframe by adding the reviewed `allow-downloads` sandbox permission to FRED's production application host.
- Cover the exact allowed and forbidden sandbox permissions in host regressions, and verify filename and bytes from a real browser download initiated in the actual production host component. Retain existing admission, protocol, origin, routing, and request-broker regressions.
- Keep the application protocol, SDK API, packages, backend APIs, deployment schema, and npm publication unchanged. The permission applies to all applications admitted through this host, not only RAGS.

## Capabilities

### New Capabilities

- `frontend-application-hosting`: browser behavior and containment of FRED's admitted application iframe. The existing canonical specs cover frontend package archives and an agent todo panel; neither owns the host iframe sandbox runtime contract.

### Modified Capabilities

None. `frontend-package-archives` already specifies host compatibility input selection, but no distributable package or package requirement changes here.

## Impact

The implementation would touch `TeamApplicationHostPage.tsx`, its focused host tests, and a real-browser production-host regression using the existing Chromium/Playwright infrastructure. The application stays responsible for its file content and filename. FRED continues to own team/application admission, bearer and service request handling, route authority, and protocol-`"1"` messaging. No RAGS source or frontend npm member changes. No matching implementation issue was found in the initial read-only GitHub search; create or identify one before implementation.
