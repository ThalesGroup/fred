import { describe, expect, it } from "vitest";
import { buildDocumentViewerPath, decodeMaybeBase64Utf8, extractH1, isPdfFile } from "./documentViewerUtils";

describe("decodeMaybeBase64Utf8", () => {
  it("decodes base64 UTF-8 content without corrupting non-ASCII text", () => {
    expect(decodeMaybeBase64Utf8("w6l0w6k=")).toBe("été");
  });

  it("returns the original string when input is not valid base64", () => {
    expect(decodeMaybeBase64Utf8("# Plain markdown")).toBe("# Plain markdown");
  });
});

describe("extractH1", () => {
  it("returns the first markdown H1 heading", () => {
    expect(extractH1("intro\n# Title\n## Subtitle")).toBe("Title");
  });

  it("returns null when no H1 exists", () => {
    expect(extractH1("## Subtitle only")).toBeNull();
  });
});

describe("isPdfFile", () => {
  it("recognizes a .pdf extension case-insensitively", () => {
    expect(isPdfFile("report.pdf")).toBe(true);
    expect(isPdfFile("REPORT.PDF")).toBe(true);
  });

  it("rejects every other extension", () => {
    expect(isPdfFile("report.docx")).toBe(false);
    expect(isPdfFile("report.pdf.docx")).toBe(false);
  });

  it("rejects a missing file name", () => {
    expect(isPdfFile(undefined)).toBe(false);
    expect(isPdfFile(null)).toBe(false);
    expect(isPdfFile("")).toBe(false);
  });
});

describe("buildDocumentViewerPath", () => {
  it("prepends the configured basename and encodes uid and query params", () => {
    const path = buildDocumentViewerPath(
      {
        uid: "doc/alpha",
        title: "My Doc",
        file_name: "folder/file.md",
        author: "Jane Doe",
        repository: "repo-a",
      },
      "/fred",
    );

    expect(path).toBe("/fred/documents/doc%2Falpha?title=My+Doc&file=folder%2Ffile.md&author=Jane+Doe&repo=repo-a");
  });

  it("omits empty params and does not duplicate the root basename slash", () => {
    const path = buildDocumentViewerPath({ uid: "doc-1" }, "/");
    expect(path).toBe("/documents/doc-1");
  });
});
