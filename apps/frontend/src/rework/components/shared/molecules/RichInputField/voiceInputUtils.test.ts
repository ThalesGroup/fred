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
