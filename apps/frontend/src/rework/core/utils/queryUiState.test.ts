// @vitest-environment happy-dom
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

import { describe, expect, it } from "vitest";
import { getQueryUiState } from "./queryUiState";

// A revalidation with data already in hand: `isFetching` without `isLoading`.
const REFETCHING = { isLoading: false, isFetching: true, isUninitialized: false, isError: false };
// The first fetch, nothing to show yet.
const FIRST_LOAD = { isLoading: true, isFetching: true, isUninitialized: false, isError: false };

describe("getQueryUiState", () => {
  it("reports loading until the query has an answer", () => {
    expect(getQueryUiState(FIRST_LOAD)).toBe("loading");
    expect(getQueryUiState({ ...REFETCHING, isUninitialized: true, isFetching: false })).toBe("loading");
  });

  it("reports loading again on every refetch by default", () => {
    expect(getQueryUiState(REFETCHING)).toBe("loading");
  });

  it("holds ready through a refetch when asked to keep the previous answer", () => {
    // What a page-level gate needs: a background revalidation must not send the
    // whole body back to a spinner and unmount everything under it.
    expect(getQueryUiState(REFETCHING, { keepPreviousWhileRefetching: true })).toBe("ready");
  });

  it("still blocks on the very first load when keeping the previous answer", () => {
    expect(getQueryUiState(FIRST_LOAD, { keepPreviousWhileRefetching: true })).toBe("loading");
  });

  it("prefers loading over a stale error, and reports the error once settled", () => {
    expect(getQueryUiState({ ...REFETCHING, isError: true })).toBe("loading");
    expect(getQueryUiState({ isLoading: false, isFetching: false, isUninitialized: false, isError: true })).toBe(
      "error",
    );
  });

  it("reports ready when nothing is in flight", () => {
    expect(getQueryUiState({ isLoading: false, isFetching: false, isUninitialized: false, isError: false })).toBe(
      "ready",
    );
  });
});
