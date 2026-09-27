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

import type {
  FredApplicationContext,
  FredApplicationRoute,
} from "@fred-oss/iframe-sdk";

declare const context: FredApplicationContext;
declare const route: FredApplicationRoute;

// @ts-expect-error The installed SDK context is an immutable snapshot.
context.team.id = "readonly-context-typecheck-only";
// @ts-expect-error The resolved host theme is immutable when present.
context.theme = "dark";
// @ts-expect-error Accepted route events are immutable payloads.
route.subPath = "readonly-route-typecheck-only";

export {};
