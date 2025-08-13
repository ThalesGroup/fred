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

import { useDrawer } from "../components/DrawerProvider";
import DocumentViewer from "./DocumentViewer";


export interface DocumentViewerDocument {
  document_uid: string;
  file_name?: string;
  file_url?: string;
  content?: string;
}

export interface DocumentViewerOptions {
  highlightedParts?: any[];
  chunksToHighlight?: string[];
}

export const useDocumentViewer = () => {
  const { openDrawer, closeDrawer } = useDrawer();

  const openDocument = (doc: DocumentViewerDocument, options?: DocumentViewerOptions) => {
    openDrawer({
      content: (
        <DocumentViewer
          document={doc}
          onClose={closeDrawer}
          highlightedParts={options?.highlightedParts}
          chunksToHighlight={options?.chunksToHighlight}
        />
      ),
      anchor: "right",
    });
  };

  const closeDocument = () => {
    closeDrawer();
  };

  return {
    openDocument,
    closeDocument,
  };
};
