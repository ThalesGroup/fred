## Decisions

1. **Cached chart values, no vision.** A chart's cached values are the only text it carries; reading them costs nothing and needs no model call.
2. **Table layout.** Categories as rows, one column per series; a pie or doughnut keeps its first series only. Capped at 50 x 10 with a truncation line.
3. **Never fail the deck.** A chart python-pptx cannot read is skipped. A slide without notes is not given an empty notes part.
