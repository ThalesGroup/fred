## 1. Shared attribution and trusted context

- [x] 1.1 Add the pure Office author formatter in `fred-core` for `KeycloakUser | None` plus a trusted fallback user ID, call it during Word export, and verify focused tests for complete names, blank-name username fallback, ID fallback, Unicode, and the 255-character boundary.
- [x] 1.2 Add `CapabilityContext.author: str | None` and pass only a string selected from the verified `KeycloakUser` without changing `CapabilityIdentity`; verify focused tests for verified and delegated subjects, context propagation, absent author, and the unchanged model-visible identity schema. Direct and streamed routes share the same execution path and receive only the authenticated subject.

## 2. PowerPoint output

- [x] 2.1 Add one PPTX core-property setter shared by the PowerPoint generation paths, with ID fallback at the tool boundary; verify a focused test reads both properties back from generated PPTX bytes and the source template remains unchanged.
- [x] 2.2 Apply attribution in PPT Filler's worker; verify focused fill tests for distinct author strings, delegated-ID fallback, and 255/256-character inputs. The shared formatter covers profile and username selection.
- [x] 2.3 Apply attribution to PPT Builder's delivered deck; verify focused build tests for the same identity cases and that preview generation does not alter the downloaded PPTX metadata.

## 3. Close-out

- [x] 3.1 Update the affected capability READMEs and add a migration note with no storage impact; verify the text matches the generated-file behavior and requires no API or schema regeneration.
- [x] 3.2 Run relevant package tests and one root `make code-quality`, then review the full branch against `origin/swift` with `audit-branch` and an independent read-only reviewer; record results and dispositions in the draft PR.
- [x] 3.3 Reconcile the OpenSpec artifacts with the implementation, validate and sync the delta specs, archive the change, and verify the resulting current specs describe both PowerPoint paths.
