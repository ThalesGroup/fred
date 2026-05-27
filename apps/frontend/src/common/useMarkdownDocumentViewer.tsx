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
import MarkdownDocumentViewer from "./MarkdownDocumentViewer";

export interface MarkdownDocumentViewer {
  document_uid: string;
  file_name?: string;
  file_url?: string;
  content?: string;
}

export interface MarkdownDocumentViewerOptions {
  highlightedParts?: any[];
  chunksToHighlight?: string[];
}

export const useMarkdownDocumentViewer = () => {
  const { openDrawer, closeDrawer } = useDrawer();

  const openMarkdownDocument = (doc: MarkdownDocumentViewer, options?: MarkdownDocumentViewerOptions) => {
    openDrawer({
      content: (
        <MarkdownDocumentViewer
          document={doc}
          onClose={closeDrawer}
          highlightedParts={options?.highlightedParts}
          chunksToHighlight={options?.chunksToHighlight}
        />
      ),
      anchor: "right",
    });
  };
  screenX;

  const closeMarkdownDocument = () => {
    closeDrawer();
  };

  return {
    openMarkdownDocument,
    closeMarkdownDocument,
  };
};
