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

/** Minimal structural shape shared by the control-plane and knowledge-flow UserSummary types. */
export interface UserNameFields {
  first_name?: string | null;
  last_name?: string | null;
  username?: string | null;
  email?: string | null;
}

/**
 * Resolve a user's display name: "First Last", falling back to username, then email.
 * Returns undefined when nothing usable is set (e.g. id-only summary for a deleted user).
 */
export function getUserDisplayName(user: UserNameFields): string | undefined {
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
  return fullName || user.username || user.email || undefined;
}
