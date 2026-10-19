## 1. Default prompt content

- [ ] 1.1 Add the current-date instruction to both English and French defaults of the generic ReAct and Deep assistants; inspect all four rendered prompt values for `{today}` and date-only wording.

## 2. Verification

- [ ] 2.1 Run the focused prompt tests and `openspec validate add-current-date-to-generic-agent-prompts --strict`; confirm the existing runtime token and override paths remain unchanged.
