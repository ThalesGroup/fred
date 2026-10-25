// Copyright Thales 2026
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

export type AccountRequest = (
  path: string,
  token: string,
  init?: { method?: string; body?: unknown },
) => Promise<{ status: number; body: unknown }>;

export class PromptLookupDenied extends Error {}

export function responseId(body: unknown): string | null {
  const id = (body as { id?: unknown } | null)?.id;
  return typeof id === "string" && id ? id : null;
}

export async function verifiedPromptIdForCommand(
  request: AccountRequest,
  path: string,
  token: string,
  command: string,
  name: string,
  text: string,
): Promise<string | null> {
  const commandPath = path.replace(/\/prompts$/, "/prompt-commands");
  const { status, body } = await request(commandPath, token);
  if (status === 403 || status === 404) throw new PromptLookupDenied(`GET ${commandPath}: HTTP ${status}`);
  if (status !== 200 || !Array.isArray(body))
    throw new Error(`GET ${commandPath}: HTTP ${status} or invalid command list`);
  const id = body.find((item) => item?.command === command)?.prompt_id;
  if (typeof id !== "string" || !id) return null;
  const exactPath = `${path}/${encodeURIComponent(id)}`;
  const prompt = await request(exactPath, token);
  if (
    prompt.status !== 200 ||
    responseId(prompt.body) !== id ||
    (prompt.body as { name?: unknown } | null)?.name !== name ||
    (prompt.body as { text?: unknown } | null)?.text !== text
  ) {
    throw new Error(
      `${commandPath}: command ${command} does not identify this run's prompt (GET ${exactPath}: HTTP ${prompt.status})`,
    );
  }
  return id;
}
