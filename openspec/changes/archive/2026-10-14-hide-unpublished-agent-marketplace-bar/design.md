## Context

`TeamMarketplaceState` currently renders a muted bar whenever its input is absent or not visible. The agent card otherwise has no separate wrapper or fixed height for that bar.

## Goals / Non-Goals

**Goal:** Omit the entire bar for states without visible publication information.

**Non-goal:** Change publication permissions, server state, or the marketplace listing cards.

## Decisions

Return no element from `TeamMarketplaceState` for absent, hidden, and non-visible Removed states. Keep the existing `showBar` team gate and the rendering for visible Published and Removed states. Remove the now-unused muted label style and translations. This leaves no bar element to occupy space or show a background.

## Risks / Trade-offs

In a grid row with both published and unpublished agents, the card shells can still align to the row height. Targeted component and page tests will check that unpublished cards have no marketplace bar element while published cards retain theirs.
