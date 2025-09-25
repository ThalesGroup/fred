// usePdfDocumentViewer.ts

import { useDrawer } from "../components/DrawerProvider";
import PdfDocumentViewer from "./PdfDocumentViewer";

export interface PdfDocumentData {
  document_uid: string;
  file_name?: string;
}

export const usePdfDocumentViewer = () => {
  const { openDrawer, closeDrawer } = useDrawer();

  const openPdfDocument = (doc: PdfDocumentData) => {
    openDrawer({
      content: (
        <PdfDocumentViewer
          document={doc}
          onClose={closeDrawer}
        />
      ),
      anchor: 'right',
    });
  };

  return { openPdfDocument, closePdfDocument: closeDrawer };
};
