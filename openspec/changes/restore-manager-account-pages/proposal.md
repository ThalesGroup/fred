## Why

During the 2026-10-18 manual recipe on `chore/rust-rebac`, the platform owner reached the empty Home view and successfully imported the demo bundle, but their account menu exposed only identity and logout. They could not open Fred's usual profile or release notes. Restore that user journey using the existing pages and shared components. The subsequent Priya recipe exposed a broader regression: Home, team navigation and routes had been replaced or removed. The developer explicitly requires the complete swift UI as the invariant for reconstruction and manual revalidation.

## What Changes

- Restore the existing Profile entry and `/settings` page after personal consent and platform bootstrap, including for a platform owner with no organization or space membership.
- Reuse `UserSettingsPage` for identity, current manager platform roles, interface theme, light/dark/system mode, language, and logout. Reuse its existing links and pages for CGU, privacy information and release notes.
- Restore the existing optional contact-support entry when configured. Keep identity/logout available before admission without protected business queries.
- Reuse the exact existing page/component implementations and styles; adapt their routing and data bindings in place. Do not introduce a manager-specific profile copy or alternate UI.
- Keep this lot independent of Python profile enrichment, photo storage and platform-announcement publication. The proposed scope omits photo upload/delete and the published "What's new" dialog; these are distinct from the static release-notes page and require separate manager contracts.

- Restore the complete existing Home, team, marketplace and administration navigation and routes, including Agents, Prompts, Resources, chat and support pages. Restore their existing presentation rather than a manager-specific subset. Organization information appears only in Profile.
- Keep non-migrated calls unchanged; the developer will stop control-plane and accepts normal request failures until the corresponding Rust contracts are rebuilt. Do not fabricate successful data, add fallback routing or remove controls to accommodate missing endpoints. Preserve manager consent/bootstrap, provisioning, membership discovery and personal opening.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `control-plane-provisioning`: extend the existing admitted account journey with the shared profile, preferences, legal pages and release notes, retaining manager authority and no implicit membership.

## Impact

Frontend router, `UserProfile`, its sidebar admission context, `UserSettingsPage`, existing legal/release pages as needed, and their tests. Use the existing generated manager `/me` and onboarding contracts; no backend API, database table, migration or new authority role is planned. Update the relevant arc42 journey/runtime/quality chapters with the implementation.

Track this reconstruction lot under [#3092](https://github.com/ThalesGroup/fred/issues/3092). The separate `reconstruct-manager-platform-admission` change concerns admission policy and is not expanded by this account-navigation work. On 2026-10-18 the developer confirmed profile, platform role, preferences, legal pages and release notes, with photos in a separate lot. The acceptance criteria below accompany that scope for implementation review; this is not a claim of full profile-feature parity.
