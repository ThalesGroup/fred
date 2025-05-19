// utils/DocumentIcon.tsx
import { PdfIcon, WordIcon, ExcelIcon } from "../../utils/icons";
export const getDocumentIcon = (filename: string): JSX.Element | null => {
  const ext = filename.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'pdf':
      return <PdfIcon style={{ width: 20, height: 20 }} />;
    case 'docx':
    case 'doc':
      return <WordIcon style={{ width: 20, height: 20 }} />;
    case 'xlsx':
    case 'xls':
      return <ExcelIcon style={{ width: 20, height: 20 }} />;
    default:
      return null;
  }
};
