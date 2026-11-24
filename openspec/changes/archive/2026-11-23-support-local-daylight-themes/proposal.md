## Why

A seasonal theme can select light and dark artwork, but a conversation and its exterior landscape cannot follow the same dawn or dusk as local time passes.

## What Changes

Allow a deployment theme to declare local sunrise and sunset. Swift supplies the current lighting to its CSS in System mode. The Christmas bundle uses 07:30 and 17:00 on the user's clock for the landscape and the conversation room.

## Capabilities

### Modified Capabilities

- `frontend-ui-themes` extends system appearance for themes that declare a daylight schedule.

## Impact

The theme catalog validator, pre-paint boot, React theme provider, authoring guides and external seasonal assets are affected. There is no backend API or stored preference migration.
