// agentSchema.ts
import { z } from "zod";
import { TFunction } from "i18next";

export const AGENT_TYPES = ["mcp"] as const;
export const MCP_TRANSPORTS = ["sse", "http"] as const;

export const createAgentSchema = (t: TFunction) => {
  const get = (key: string, defaultValue?: string) => t(key, { defaultValue });

  const mcpServerSchema = z.object({
    name: z.string().min(1, { message: get("validation.required", "Required") }),
    url: z.url({ message: get("validation.invalid_url", "Invalid URL") }),
    transport: z.enum(MCP_TRANSPORTS), // or .refine(() => true, { message: ... })
    sse_read_timeout: z.number().min(0, { message: get("validation.timeout_min", "Must be ≥ 0") }).optional(),
  });

  return z.object({
    name: z.string().min(1, { message: get("validation.required", "Required") }),
    nickname: z.string().min(1, { message: get("validation.required", "Required") }),
    description: z.string().min(1, { message: get("validation.required", "Required") }),
    role: z.string().min(1, { message: get("validation.required", "Required") }),

    base_prompt: z.string().min(1, { message: get("validation.required", "Required") }),
    icon: z.string().optional(),

    agent_type: z.literal("mcp", { message: get("validation.invalid_type", "Invalid type") }),

    categories: z.array(z.string()).optional(),
    mcp_servers: z.array(mcpServerSchema).min(1, { message: get("validation.required", "Required") }),
  });
};
