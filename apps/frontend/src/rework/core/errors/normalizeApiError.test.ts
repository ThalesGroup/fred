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

import { describe, it, expect } from "vitest";
import { normalizeApiError } from "./normalizeApiError";

describe("normalizeApiError", () => {
  describe("non-shaped input", () => {
    it("returns unknown for null / primitives / undefined", () => {
      expect(normalizeApiError(null)).toEqual({ kind: "unknown" });
      expect(normalizeApiError(undefined)).toEqual({ kind: "unknown" });
      expect(normalizeApiError("boom")).toEqual({ kind: "unknown" });
      expect(normalizeApiError(42)).toEqual({ kind: "unknown" });
    });

    it("returns unknown for an object without a status field", () => {
      expect(normalizeApiError({ data: { detail: "nope" } })).toEqual({ kind: "unknown" });
    });

    it("returns unknown when status is neither string nor number", () => {
      expect(normalizeApiError({ status: null })).toEqual({ kind: "unknown" });
      expect(normalizeApiError({ status: { weird: true } })).toEqual({ kind: "unknown" });
    });
  });

  describe("string status (RTK Query transport errors)", () => {
    it("maps FETCH_ERROR to network with the error message", () => {
      expect(normalizeApiError({ status: "FETCH_ERROR", error: "Failed to fetch" })).toEqual({
        kind: "network",
        detail: "Failed to fetch",
      });
    });

    it("maps TIMEOUT_ERROR to network", () => {
      expect(normalizeApiError({ status: "TIMEOUT_ERROR", error: "timed out" })).toEqual({
        kind: "network",
        detail: "timed out",
      });
    });

    it("network detail is omitted when error message is missing/blank", () => {
      expect(normalizeApiError({ status: "FETCH_ERROR", error: "   " })).toEqual({
        kind: "network",
        detail: undefined,
      });
    });

    it("maps other string statuses (e.g. PARSING_ERROR) to unknown with detail", () => {
      expect(normalizeApiError({ status: "PARSING_ERROR", error: "bad json" })).toEqual({
        kind: "unknown",
        detail: "bad json",
      });
    });
  });

  describe("numeric status", () => {
    it.each([
      [403, "forbidden"],
      [409, "conflict"],
      [400, "validation"],
      [422, "validation"],
      [500, "unknown"],
      [404, "unknown"],
    ] as const)("maps HTTP %i to %s", (status, kind) => {
      expect(normalizeApiError({ status })).toEqual({ kind, status });
    });

    it("includes status on the result", () => {
      expect(normalizeApiError({ status: 403 }).status).toBe(403);
    });
  });

  describe("detail extraction from data", () => {
    it("uses data.detail when it is a non-empty string", () => {
      expect(normalizeApiError({ status: 400, data: { detail: "Name is required" } })).toEqual({
        kind: "validation",
        status: 400,
        detail: "Name is required",
      });
    });

    it("ignores a blank data.detail", () => {
      expect(normalizeApiError({ status: 400, data: { detail: "  " } }).detail).toBeUndefined();
    });

    it("falls back to the first errors[].detail", () => {
      const error = { status: 422, data: { errors: [{}, { detail: "Field invalid" }] } };
      expect(normalizeApiError(error).detail).toBe("Field invalid");
    });

    it("falls back to errors[].message when detail is absent", () => {
      const error = { status: 422, data: { errors: [{ message: "Bad value" }] } };
      expect(normalizeApiError(error).detail).toBe("Bad value");
    });

    it("returns no detail when data has neither detail nor a usable errors array", () => {
      expect(normalizeApiError({ status: 409, data: { errors: "not-an-array" } }).detail).toBeUndefined();
      expect(normalizeApiError({ status: 409, data: {} }).detail).toBeUndefined();
      expect(normalizeApiError({ status: 409 }).detail).toBeUndefined();
    });
  });
});
