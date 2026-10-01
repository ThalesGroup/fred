# fred-capability-pptx-generator

Fred agent capability that composes a PowerPoint deck **from scratch** — title,
multiple slides, bullet content, tables, native charts, images, and speaker
notes — in a single tool call.

Unlike `fred-capability-ppt-filler` (which fills an uploaded template's
placeholders), this capability's tool schema is static: an agent asks for a
deck's structure directly, it never needs a pre-existing `.pptx` to fill. An
optional brand-template upload (masters/theme only, nothing parsed) lets the
generated deck match corporate branding.

Charts prefer native, PowerPoint-editable objects (bar, column, line, pie,
doughnut, area, radar, scatter, bubble via `python-pptx`'s `XL_CHART_TYPE`);
chart types `python-pptx` cannot express natively (heatmap, waterfall,
funnel, Gantt) render as a `matplotlib` image embedded on the slide — the
choice is made at build time, transparent to the agent.

## Spec

The design lives in `docs/swift/rfc/PPTX-GENERATOR-CAPABILITY-RFC.md`.

## Registration

Installing this package *is* the registration: the fred-agents pod
auto-discovers the capability at boot via the `fred.capabilities` entry point
declared in `pyproject.toml`
(`pptx_generator = "fred_capability_pptx_generator.capability:PptxGeneratorCapability"`).
