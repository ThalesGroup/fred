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

// utils/DocumentIcon.tsx
import React, { useMemo, useState } from "react";
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFile";
import { ExcelIcon, PdfIcon, WordIcon, PowerPointIcon, MarkdownIcon, TextIcon } from "../../../utils/icons";

type ExtIconProps = { ext?: string; size?: number };

// Try to render a static SVG from public folder if available: /images/filetypes/<ext>.svg
// Falls back to built-in vector icons, then to a generic file icon.
const ExtIcon: React.FC<ExtIconProps> = ({ ext, size = 20 }) => {
  const [imgOk, setImgOk] = useState(true);
  const style = useMemo(() => ({ width: size, height: size, display: "inline-block" }), [size]);
  const baseUrl = (import.meta.env.BASE_URL ?? "/").endsWith("/")
    ? (import.meta.env.BASE_URL ?? "/")
    : `${import.meta.env.BASE_URL ?? "/"}/`;

  // Built-in mapping for common types
  const builtIn = useMemo(() => {
    switch (ext) {
      case "pdf":
        return <PdfIcon style={style} />;
      case "doc":
      case "docx":
        return <WordIcon style={style} />;
      case "xls":
      case "xlsx":
      case "csv":
        return <ExcelIcon style={style} />;
      case "ppt":
      case "pptx":
        return <PowerPointIcon style={style} />;
      case "md":
        return <MarkdownIcon style={style} />;
      case "txt":
        return <TextIcon style={style} />;
      default:
        return null;
    }
  }, [ext, style]);

  if (ext && imgOk) {
    const src = `${baseUrl}images/filetypes/${ext}.svg`;
    return (
      <img
        src={src}
        alt={ext}
        style={style as React.CSSProperties}
        onError={() => setImgOk(false)}
        loading="lazy"
      />
    );
  }

  return builtIn ?? <InsertDriveFileIcon style={style} />;
};

export const getDocumentIcon = (filename: string): JSX.Element | null => {
  const ext = filename.split(".").pop()?.toLowerCase();
  return <ExtIcon ext={ext} />;
};
