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
import { useDispatch } from "react-redux";
import type { ThunkDispatch, UnknownAction } from "@reduxjs/toolkit";

/** Dispatches generated-client endpoints with initiate, as the signed-in admin. */
export type ApiDispatch = ThunkDispatch<unknown, unknown, UnknownAction>;

export function useApiDispatch(): ApiDispatch {
  return useDispatch<ApiDispatch>();
}

/** A one-shot read: never served from cache, never kept subscribed. */
export const FRESH = { subscribe: false, forceRefetch: true } as const;
