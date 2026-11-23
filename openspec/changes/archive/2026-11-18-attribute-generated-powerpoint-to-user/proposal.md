## Why

PowerPoint files generated from an uploaded template retain the template creator in their Author and Last modified by properties. PRISM-263 reports that the downloaded file should identify the person who used the capability, matching Word export behavior in #3422.

## What Changes

- Attribute newly generated PPT Filler and PPT Builder downloads to the acting user instead of retaining template metadata.
- Use the same name selection rule as Word export: trimmed first and last name when both are available, otherwise the authenticated username. Keep values within the Office core property limit.
- Pass the verified user in `CapabilityContext.author` and select the Office author at each document save point. Share selection and property assignment between Word and PowerPoint.
- Preserve templates and previously downloaded files. Deck content, preview, download access, and filenames stay as they are.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ppt-filler`: Filled deck downloads carry the acting user's attribution.
- `ppt-builder`: Built deck downloads carry the acting user's attribution.

## Impact

The runtime must pass trusted user attribution to capability execution. The SDK capability context, both PowerPoint generation paths, and Word's existing attribution path are affected. `CapabilityIdentity` remains unchanged. No database, frontend API, or new identity-provider request is planned. See PRISM-263 and #3422.
