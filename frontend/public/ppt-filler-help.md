# PowerPoint Filler — how it works

The **PowerPoint Filler** toolkit turns an agent into a generator of branded,
ready-to-send PowerPoint decks. You bring **your own** `.pptx` template; the agent
extracts the right values from the conversation (and any attached documents) and fills
your template for you. The end user receives a download link to the finished deck.

You stay in control of the design: the uploaded template is the single source of truth.
You decide where values go and how each one should be filled.

---

## What you upload

A single `.pptx` template. Inside it, you mark the places to fill with **keys** and you
describe each key in that slide's **speaker notes**.

### 1. Mark the values with `{{key}}`

In any text box, write a key wrapped in double braces:

```
Client: {{clientName}}
Mission: {{mission}}
```

- Use the **same key several times on one slide** to repeat a value (for example a name
  in a header and a footer) — every occurrence is filled with the same value.
- The **same key on a different slide is independent** — it has its own description and
  its own value.

### 2. Describe each key in the slide notes

Open the slide's **notes** (View → Notes) and, for each key, write a header line
`{{key}}:` followed by a free-text description. The description tells the agent what to
put there.

```
{{clientName}}:
The name of the client company the proposal is addressed to.

{{mission}}:
A one-sentence summary of the mission, written for a business audience.
```

A header line is **only** a header when it is exactly one or more `{{key}}` tokens
ending in a colon. A line that merely mentions `{{something}}` in the middle of a
sentence is treated as ordinary description text — so you can write naturally.

---

## Notation in detail

### Multi-line descriptions

A description runs from its header until the next header (or the end of the notes), so it
can span several lines, including blank lines:

```
{{context}}:
The business context of the mission.

Mention the client's industry and the main constraints
(regulatory, technical, budget).
```

### One description for several keys

Describe related keys together by listing them, comma-separated, on the header line. They
all receive the same description:

```
{{firstName}}, {{lastName}}:
The consultant's name, as it should appear on the cover slide.
```

### Keeping real speaker notes in the result

By default, your `{{key}}:` descriptions are **authoring instructions** and are
**removed** from the filled deck — the end user never sees them.

If you also want **real speaker notes** to stay in the result, add a line of **dashes
(at least three)** after your descriptions. Everything **below** that line is kept
verbatim in the filled deck; everything above it (the descriptions) is stripped.

```
{{mission}}:
A one-sentence summary of the mission.

---
Speaker note: keep this slide under two minutes and end on the budget.
```

In the filled deck, this slide's notes will contain only:

```
Speaker note: keep this slide under two minutes and end on the budget.
```

A line with fewer than three dashes (for example `--`) is **not** a separator and stays
as ordinary text.

---

## Immediate feedback

When you upload a template, it is analyzed right away and you see, **per slide**, the
keys it found together with their descriptions — before you save the agent.

If something is off, you get a clear, slide-numbered message:

- **A key has no description** — a `{{key}}` appears in a text box but is not described in
  that slide's notes. Add the missing description.
- **A description points to a missing key** — the notes describe a `{{key}}` that does not
  appear in any text box on that slide. Fix the typo or remove the stale description.

You cannot save the agent until the template is valid, so a broken configuration never
reaches your users.

---

## Good to know

- Only standard **text boxes** are filled. Table cells and grouped shapes are not
  supported yet.
- The agent decides the **values** from the conversation and your descriptions — keep the
  descriptions specific so it fills the right thing.
- Replacing the template re-analyzes it; the schema always matches the actual file.
