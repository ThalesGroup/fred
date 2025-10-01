// agents.ts (frontend)

import { Agent, Leader } from "../slices/agentic/agenticOpenApi";

export type AnyAgent =
  | ({ type: "agent" } & Agent)
  | ({ type: "leader" } & Leader);

export const isLeader = (a: AnyAgent): a is ({ type: "leader" } & Leader) =>
  a.type === "leader";
