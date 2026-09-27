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

import { appendVoiceTranscript, audioFileExtensionForMimeType } from "./voiceInputUtils";

describe("appendVoiceTranscript", () => {
  it("uses the transcript directly when the input is empty", () => {
    expect(appendVoiceTranscript("", "  hello world  ")).toBe("hello world");
  });

  it("appends with one separating space when the input has text", () => {
    expect(appendVoiceTranscript("Need a summary", "of this file")).toBe("Need a summary of this file");
  });

  it("reuses trailing whitespace when already present", () => {
    expect(appendVoiceTranscript("Need a summary:\n", "of this file")).toBe("Need a summary:\nof this file");
  });

  it("keeps the current value when the transcript is blank", () => {
    expect(appendVoiceTranscript("Keep this", "   ")).toBe("Keep this");
  });
});

describe("audioFileExtensionForMimeType", () => {
  it("maps common mime types to stable file extensions", () => {
    expect(audioFileExtensionForMimeType("audio/webm")).toBe(".webm");
    expect(audioFileExtensionForMimeType("audio/ogg;codecs=opus")).toBe(".ogg");
    expect(audioFileExtensionForMimeType("audio/wav")).toBe(".wav");
    expect(audioFileExtensionForMimeType("audio/mp4")).toBe(".m4a");
  });
});
