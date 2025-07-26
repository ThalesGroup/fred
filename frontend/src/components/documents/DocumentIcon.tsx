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
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFile";
import { ExcelIcon, PdfIcon, WordIcon } from "../../utils/icons";

export const getDocumentIcon = (filename: string): JSX.Element | null => {
  const ext = filename.split(".").pop()?.toLowerCase();
  const style = { width: 20, height: 20 };

  switch (ext) {
    case "pdf":
      return <PdfIcon style={style} />;
    case "docx":
    case "doc":
      return <WordIcon style={style} />;
    case "xlsx":
    case "xls":
      return <ExcelIcon style={style} />;
    case "csv":
      return <ExcelIcon style={style} />;
    default:
      return <InsertDriveFileIcon style={style} />;
  }
};
