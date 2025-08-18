// src/common/mime.ts
import type { ComponentType } from "react";
import { WordIcon, PowerPointIcon, PdfIcon, MarkdownIcon } from "../assets/icons";
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFile";

export function mimeMeta(mime?: string | null): { label: string; Icon: ComponentType<any> } {
  const m = (mime || "").toLowerCase();
  if (m.includes("pdf")) return { label: "PDF", Icon: PdfIcon };
  if (m.includes("wordprocessingml.document") || m.includes("msword"))
    return { label: "Word (DOCX)", Icon: WordIcon };
  if (m.includes("presentationml.presentation") || m.includes("vnd.ms-powerpoint"))
    return { label: "PowerPoint (PPTX)", Icon: PowerPointIcon };
  if (m.includes("markdown")) return { label: "Markdown", Icon: MarkdownIcon };
  return { label: "File", Icon: InsertDriveFileIcon };
}
