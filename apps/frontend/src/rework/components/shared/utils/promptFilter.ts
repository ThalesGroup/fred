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

// Search + category predicate shared by the team prompts page and the chat's
// prompt-selection panel, so the two lists narrow identically.

/** The fields both prompt payloads expose; narrower than either full type. */
export interface FilterablePrompt {
  name: string;
  description?: string | null;
  category_id?: string | null;
}

/**
 * Sentinel category id for "prompts with no category at all". Not a real
 * category, so it can never collide with a server-issued id.
 */
export const NO_CATEGORY_FILTER_ID = "__no_category__";

export interface PromptFilterCriteria {
  /** Raw input value; empty or whitespace-only matches everything. */
  search: string;
  /** `null` means every category. */
  categoryId: string | null;
  /**
   * The categories that actually exist. When given, a prompt pointing at a
   * category outside this set counts as uncategorised rather than falling out
   * of every chip — a category can be deleted while prompts still reference
   * it. Omit to trust `category_id` as-is.
   */
  knownCategoryIds?: ReadonlySet<string>;
}

/** Case-insensitive substring match over name + description. */
function matchesSearch(prompt: FilterablePrompt, query: string): boolean {
  if (!query) return true;
  return [prompt.name, prompt.description]
    .filter(Boolean)
    .some((field) => (field as string).toLowerCase().includes(query));
}

function matchesCategory(
  prompt: FilterablePrompt,
  categoryId: string | null,
  knownCategoryIds?: ReadonlySet<string>,
): boolean {
  if (!categoryId) return true;
  const { category_id: id } = prompt;
  if (categoryId === NO_CATEGORY_FILTER_ID) {
    return !id || (knownCategoryIds !== undefined && !knownCategoryIds.has(id));
  }
  return id === categoryId;
}

export function filterPrompts<T extends FilterablePrompt>(prompts: T[], criteria: PromptFilterCriteria): T[] {
  const query = criteria.search.trim().toLowerCase();
  return prompts.filter(
    (prompt) => matchesSearch(prompt, query) && matchesCategory(prompt, criteria.categoryId, criteria.knownCategoryIds),
  );
}
