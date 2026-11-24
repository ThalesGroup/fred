## Context

Appearance is resolved before React mounts and is also consumed by React, CSS and hosted UI. The deployment theme is installed from S3 and served by the frontend. External SVG background images do not inherit document CSS variables.

## Decisions

- The optional catalog field `localDaylight` holds ordered local clock strings `sunrise` and `sunset`. Use the same schedule at boot and during the session. Manual modes use the existing artwork. Ordinary System mode continues to follow the operating system.
- Derive dawn, day, dusk and night from local civil time, including after the device wakes or changes timezone. Publish interpolation values on the document. Update only an active clock theme with bounded browser-local work. No server polling, location or Internet lookup is involved.
- The Christmas archive supplies the colours and scene layers. The sun and moon cross the landscape and illuminate the room window. Updates change presentation in place while messages, scroll state and independent animations continue. Preserve message contrast and reduced motion.

## Rollout

Deploy frontend support before installing an archive containing the optional field. Older archives continue to work with the updated frontend.
