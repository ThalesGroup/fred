import type {
  FredApplicationContext,
  FredApplicationRoute,
} from "@fred/iframe-sdk";

declare const context: FredApplicationContext;
declare const route: FredApplicationRoute;

// @ts-expect-error The installed SDK context is an immutable snapshot.
context.team.id = "readonly-context-typecheck-only";
// @ts-expect-error Accepted route events are immutable payloads.
route.subPath = "readonly-route-typecheck-only";

export {};
