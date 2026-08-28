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

The generated frontend registry, runtime service contract, and Control Plane
catalog remain Fred-owned build outputs. Regenerate them from the frontend
project after changing an application package.
