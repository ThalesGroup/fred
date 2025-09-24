// agentSchema.ts
import { z } from "zod";
import { TFunction } from "i18next";

export const MCP_TRANSPORTS = ["streamable_http", "http"] as const;

export const createMcpAgentSchema = (t: TFunction) => {
  const get = (key: string, defaultValue?: string) => t(key, { defaultValue });

  const mcpServerSchema = z.object({
    name: z.string().min(1, { message: get("validation.required", "Required") }),
    url: z.url({ message: get("validation.invalid_url", "Invalid URL") }),
    transport: z.enum(MCP_TRANSPORTS), // or .refine(() => true, { message: ... })
    sse_read_timeout: z
      .number()
      .min(0, { message: get("validation.timeout_min", "Must be ≥ 0") })
      .optional(),
  });

  return z.object({
    name: z.string().min(1, { message: get("validation.required", "Required") }),
    description: z.string().min(1, { message: get("validation.required", "Required") }),
    role: z.string().min(1, { message: get("validation.required", "Required") }),
    tags: z.array(z.string()).optional(),
    mcp_servers: z.array(mcpServerSchema).min(1, { message: get("validation.required", "Required") }),
  });
};
