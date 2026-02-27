import type { TokenUsageSource } from "../../slices/agentic/agenticOpenApi";

const assertNever = (value: never): never => {
  throw new Error(`Unhandled TokenUsageSource value: ${String(value)}`);
};

export const tokenUsageSourceLabel = (source: TokenUsageSource | null | undefined): string | undefined => {
  if (!source) return undefined;
  switch (source) {
    case "updates":
      return "updates";
    case "messages":
      return "messages";
    case "messages_backfill":
      return "messages (backfill)";
    case "unavailable":
      return "unavailable";
    default:
      return assertNever(source);
  }
};
