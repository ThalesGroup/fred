## 1. Automatic clipboard copy

- [x] 1.1 Copy each newly generated URL through the existing clipboard path without extending global busy state; verify successful creation writes the expected URL and shows copy confirmation.
- [x] 1.2 Preserve the generated URL and manual retry when clipboard writing fails; verify a failed write does not report failed generation or create a second link.
- [x] 1.3 Ignore delayed clipboard results after dismissal or a newer copy; verify both cases with deferred clipboard tests.
- [x] 1.4 Render the generated URL with Fred's monospace font and verify its computed font in the browser.

## 2. Contract and validation

- [x] 2.1 Update the compact component UX guide and validate the OpenSpec delta against the current platform access spec.
- [x] 2.2 Inspect the generated-link dialog in the browser and run the focused frontend tests and root quality gate.
