import type { LogEventDto } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export type Level = LogEventDto["level"];
export type ServiceId = "knowledge-flow" | "agentic";

export const LEVELS: Level[] = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];

export const SERVICE_OPTIONS: { id: ServiceId; label: string }[] = [
  { id: "knowledge-flow", label: "Knowledge Flow" },
  { id: "agentic", label: "Agentic" },
];
