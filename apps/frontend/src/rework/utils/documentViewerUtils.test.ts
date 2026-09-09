import { describe, expect, it } from "vitest";
import {
  buildDocumentViewerPath,
  decodeMaybeBase64Utf8,
  documentPdfSourceUrl,
  extractH1,
  hasNativePreview,
  isOfficeDocumentFile,
  isPdfFile,
} from "./documentViewerUtils";

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

describe("isOfficeDocumentFile", () => {
  it("accepts the Word and PowerPoint formats the backend renders as PDF", () => {
    expect(isOfficeDocumentFile("rapport.docx")).toBe(true);
    expect(isOfficeDocumentFile("note.DOC")).toBe(true);
    expect(isOfficeDocumentFile("compte-rendu.odt")).toBe(true);
    expect(isOfficeDocumentFile("deck.pptx")).toBe(true);
    expect(isOfficeDocumentFile("vieux-deck.PPT")).toBe(true);
  });

  it("rejects formats the render endpoint would 415 on", () => {
    // Kept in step with PDF_RENDERABLE_SUFFIXES in content_service.py: listing a
    // format here that the backend refuses would offer a toggle that cannot load.
    expect(isOfficeDocumentFile("agence.xlsx")).toBe(false);
    // .odp is a presentation too, but no ingestion processor accepts it.
    expect(isOfficeDocumentFile("slides.odp")).toBe(false);
    expect(isOfficeDocumentFile("facture.pdf")).toBe(false);
    expect(isOfficeDocumentFile(undefined)).toBe(false);
  });
});

describe("hasNativePreview", () => {
  it("is true for the formats with a renderer distinct from their markdown extraction", () => {
    expect(hasNativePreview("facture.pdf")).toBe(true);
    expect(hasNativePreview("rapport.docx")).toBe(true);
    expect(hasNativePreview("compte-rendu.odt")).toBe(true);
    expect(hasNativePreview("deck.pptx")).toBe(true);
  });

  it("is false for formats already displayed as markdown, so no inert toggle is offered", () => {
    // An xlsx/csv preview IS the markdown extraction — there is no second
    // rendering to switch to.
    expect(hasNativePreview("agence.xlsx")).toBe(false);
    expect(hasNativePreview("ticket-jira.csv")).toBe(false);
  });

  it("is false when the file name is unknown", () => {
    expect(hasNativePreview(undefined)).toBe(false);
    expect(hasNativePreview(null)).toBe(false);
  });
});

describe("documentPdfSourceUrl", () => {
  it("streams a PDF from storage untouched", () => {
    expect(documentPdfSourceUrl("abc", "facture.pdf")).toBe("/knowledge-flow/v1/raw_content/stream/abc");
  });

  it("routes a Word document through the render endpoint", () => {
    expect(documentPdfSourceUrl("abc", "rapport.docx")).toBe("/knowledge-flow/v1/raw_content/pdf/abc");
  });

  it("routes a PowerPoint deck through the same render endpoint", () => {
    expect(documentPdfSourceUrl("abc", "deck.pptx")).toBe("/knowledge-flow/v1/raw_content/pdf/abc");
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
