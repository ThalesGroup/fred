## Context

See [proposal.md](proposal.md). `ppt_filler/fill.py` and `ppt_builder/render.py` both open a template and save a new presentation without replacing its core properties. Word export selects a name from the authenticated `KeycloakUser` in its route and sets both properties during DOCX conversion (#3422). Capability execution currently receives `CapabilityIdentity.user_id` but no display name. The runtime execution route has a verified `KeycloakUser` or a trusted delegated `AssertedUser`; the latter contains only a user ID.

## Goals / Non-Goals

**Goals:** Reuse one bounded Office author-name selection rule across Word and PowerPoint. Pass the verified `KeycloakUser` through the trusted per-turn capability context, without changing `CapabilityIdentity` or exposing the user as a model tool argument. Select the Office author string only when generating the file. Keep generation independent of extra directory or database lookups.

**Non-Goals:** Rewriting templates or existing downloads, changing PDF preview metadata, adding profile fields to public execution requests, or changing document ownership and download authorization.

## Decisions

1. Put a small pure Office author formatter in `fred-core`, which both capability packages and `fred-runtime` already depend on. It accepts a verified `KeycloakUser | None` and a trusted fallback user ID, trims names, uses the complete first-and-last pair only, otherwise uses the username, and finally falls back to the ID. It bounds the result to 255 characters. Word's export route calls it at DOCX conversion instead of repeating the selection rule; its converter keeps its own 255-character guard for direct callers. Sharing a PowerPoint-specific property setter with Word would couple two different document libraries, so PowerPoint gets one local setter used by both generation paths.
2. Add `author: KeycloakUser | None` to the SDK's `CapabilityContext`, leaving `CapabilityIdentity` as the minimal user/session/team/instance identity slice. `fred-sdk` already depends on `fred-pod`, which defines `KeycloakUser`. The runtime passes the verified `KeycloakUser` from the execution route into each context without converting it to a display string. A delegated `AssertedUser` has no profile, so `author` is `None` and the final formatter uses `identity.user_id`. The field is per-turn execution data, not a persisted capability setting or a model-visible tool argument. The runtime ignores any client-provided attribution when creating the context. A context without `author` also uses `identity.user_id`, so an older runtime or direct invocation cannot retain the template creator. Passing the verified object with the turn avoids process-local state across replicas.
3. At the final PPTX save, format `context.author` with `context.identity.user_id` as fallback, then set both `presentation.core_properties.author` and `last_modified_by` on the generated `Presentation` before saving its bytes. PPT Filler does this in its synchronous fill worker. PPT Builder does it on its rendered deck before creating the downloadable bytes; preview processing must not replace the delivered attribution. Neither path modifies the source template.

## Risks / Trade-offs

- [Delegated calls contain no profile name] -> Use the verified user ID as the fallback, as in the delegated Word handling, and never preserve the template creator. A profile lookup would add a request and a failure mode to the hot path.
- [The full `KeycloakUser` contains security and profile fields beyond the author name] -> Keep it in trusted in-process context only; do not serialize, log, persist, or pass it through model tool schemas. Only the verified subject supplies `CapabilityContext.author`; tests cover an attempted payload override.
- [Long or unusual names can fail Office property validation] -> Trim only outer whitespace, preserve Unicode and XML-sensitive text handled by the library, and limit to 255 characters before assignment.
- [The reporter's production version is not yet identified] -> Keep Jira in analysis until the affected deployment and capability are confirmed; the fix covers both source paths.

## Migration Plan

No schema or stored-data migration. Deploy the runtime, SDK, `fred-core`, Word capability, and PowerPoint capability together through the normal package release path. Reverting the change restores the previous output behavior. Existing files retain their old metadata; regenerating produces corrected files.
