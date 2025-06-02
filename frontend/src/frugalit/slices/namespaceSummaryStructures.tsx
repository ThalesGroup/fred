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

export interface NamespaceSummary {
  namespace_summary: string;
}

// Define default values for Essentials
const defaultNamespaceSummary: NamespaceSummary = {
  namespace_summary: "none",
};

/**
 * Create an Essentials object with default values.
 * @param props Partial<Essentials> with fields to override in the default Essentials object.
 * @returns An Essentials object with the default values overridden by any provided props.
 */
export function createNamespaceSummary(props: Partial<NamespaceSummary> = {}): NamespaceSummary {
  return { ...defaultNamespaceSummary, ...props };
}
