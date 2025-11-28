// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
import { TFunction } from "i18next";
import { z } from "zod";

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
