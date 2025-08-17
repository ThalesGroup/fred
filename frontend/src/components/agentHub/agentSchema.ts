// agentSchema.ts
import { z } from "zod";
import { TFunction } from "i18next";

// Local literals (you can widen later if backend supports more)
const agentTypes = ["mcp"] as const;
const mcpTransports = ["sse", "http"] as const;

export const createAgentSchema = (t: TFunction) => {
  const get = (key: string, defaultValue?: string) => t(key, { defaultValue });

  const mcpServerSchema = z.object({
    name: z.string().min(1, { message: get("validation.required", "Required") }),
    url: z.string().url({ message: get("validation.invalid_url", "Invalid URL") }),
    transport: z.enum(mcpTransports, {
      message: get("validation.invalid_transport", "Invalid transport"),
    }),
    sse_read_timeout: z
      .number()
      .min(0, { message: get("validation.timeout_min", "Must be ≥ 0") })
      .optional(),
  });

  return z.object({
    name: z.string().min(1, { message: get("validation.required", "Required") }),
    nickname: z.string().min(1, { message: get("validation.required", "Required") }),
    description: z.string().min(1, { message: get("validation.required", "Required") }),
    role: z.string().min(1, { message: get("validation.required", "Required") }),

    // ✅ REQUIRED to satisfy McpAgentRequest
    base_prompt: z.string().min(1, { message: get("validation.required", "Required") }),

    icon: z.string().optional(),

    // ✅ literal "mcp"
    agent_type: z.literal(agentTypes[0], {
      errorMap: () => ({ message: get("validation.invalid_type", "Invalid type") }),
    }),

    categories: z.array(z.string()).optional(),

    // ✅ REQUIRED array (min 1) to satisfy McpAgentRequest
    mcp_servers: z.array(mcpServerSchema).min(1, { message: get("validation.required", "Required") }),
  });
};
