import { z } from "zod";
import { TFunction } from "i18next";

import { agentTypes, mcpTransports } from "../../slices/chatApiStructures";

// Ensure Zod gets literal values, not union types
export const createAgentSchema = (t: TFunction) => {
  const get = (key: string, defaultValue?: string) => t(key, { defaultValue });
  return z.object({
    name: z.string().min(1, { message: get("validation.required", "Required") }),
    nickname: z.string().min(1, { message: get("validation.required", "Required") }),
    description: z.string().min(1, { message: get("validation.required", "Required") }),
    role: z.string().min(1, { message: get("validation.required", "Required") }),
    base_prompt: z.string().optional(),
    icon: z.string().optional(),

    agent_type: z.enum(agentTypes, {
      message: get("validation.invalid_type", "Invalid type"),
    }),

    categories: z.array(z.string()).optional(),

    mcp_servers: z
      .array(
        z.object({
          name: z.string().min(1, { message: get("validation.required", "Required") }),
          url: z.url({ message: get("validation.invalid_url", "Invalid URL") }),
          transport: z.enum(mcpTransports, {
            message: get("validation.invalid_transport", "Invalid transport"),
          }),
          sse_read_timeout: z
            .number()
            .min(0, { message: get("validation.timeout_min", "Must be ≥ 0") })
            .optional(),
        })
      )
      .optional(),
  });
}

//export type CreateAgentSchema = ReturnType<typeof createAgentSchema>;
