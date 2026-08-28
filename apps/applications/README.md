# Integrated application packages

Each bundled application lives in one self-contained package:

```text
apps/applications/<application-id>/
├── fred-app.json
├── frontend/
│   ├── index.tsx
│   └── Application.module.css
└── backend/
    └── README.md
```

`fred-app.json` is the authored installation manifest. The `frontend/`
directory contains the application module compiled into the Fred frontend.
The `backend/` directory is reserved for an independently built application
service when the manifest sets `service_required` to `true`.

The generated frontend registry and runtime service contract are tracked
Fred-owned artifacts. Regenerate and commit them after changing an application
package. The Control Plane catalog is generated from the same manifests before
Control Plane builds, tests, packaging, and image creation. It is ignored by
Git and must not be committed or edited by hand. Source-checkout Control Plane
builds require Node.js 22.13 or newer; builds from a packaged source archive
reuse the validated catalog embedded in that archive.
