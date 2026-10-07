## Decisions

- The surface rule targets behavioral variants (selection, push/resizable/floating
  drawers, standalone pagination), where hidden interaction logic lives. Optional
  presentational props of a public component stay public without separate evidence.
- Overlay focus containment is a FRED-wide behavior change, tracked separately;
  the hosted contract documents the current behavior instead of diverging from FRED.
