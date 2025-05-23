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

// A fact is a business information that explain some usage, SLAs or
// any important information that is useful to understand the role
// of  component, a namespace or an entire application.
export enum FactType {
    DOMAIN = "domain",
    REQUIREMENT = "requirement",
    COST = "cost",
    COMPLIANCE = "compliance",
    SECURITY = "security"
}

export interface Fact {
    content: string
    user: string
    date: string
    title: string
    type?: FactType; 
}
export interface FactList {
    facts: Fact[]
}
const defaultFactList: FactList = {
    facts: []
}
export function createFactList(props: Partial<FactList> = {}): FactList {
    return { ...defaultFactList, ...props };
}   