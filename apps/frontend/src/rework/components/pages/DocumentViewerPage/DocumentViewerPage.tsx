// Copyright Thales 2026
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

import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import { DocumentViewer } from "@shared/organisms/DocumentViewer/DocumentViewer";
import { extractH1 } from "../../../utils/documentViewerUtils";
import styles from "./DocumentViewerPage.module.css";

export default function DocumentViewerPage() {
  const { uid } = useParams<{ uid: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [infoOpen, setInfoOpen] = useState(false);
  const [derivedTitle, setDerivedTitle] = useState<string | null>(null);

  // Drop the previous document's derived title as soon as the route targets a
  // new one, so a stale H1 never lingers while the new document's fetch is
  // still in flight (it's only ever a fallback — recomputed once `onLoaded`
  // fires again for the current `uid`).
  useEffect(() => {
    setDerivedTitle(null);
  }, [uid]);

  const paramTitle = searchParams.get("title");
  const paramFile = searchParams.get("file");
  const paramAuthor = searchParams.get("author");
  const paramRepo = searchParams.get("repo");

  if (!uid) return null;

  const title = paramTitle ?? derivedTitle ?? paramFile ?? uid;

  const handleBack = () => {
    if (window.history.length <= 1) {
      window.close();
    } else {
      navigate(-1);
    }
  };

  const hasInfo = !!(paramTitle || paramFile || paramAuthor || paramRepo);

  return (
    <div className={styles.page}>
      <header className={styles.topBar}>
        <IconButton
          color="on-surface"
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "arrow_back" }}
          aria-label="Back"
          onClick={handleBack}
        />
        <span className={styles.title}>{title}</span>
        {hasInfo && (
          <IconButton
            color="on-surface"
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "info" }}
            aria-label="Document information"
            onClick={() => setInfoOpen(true)}
          />
        )}
      </header>

      <div className={styles.body}>
        <main className={styles.content}>
          <DocumentViewer
            documentUid={uid}
            fileName={paramFile}
            onMarkdownLoaded={(c) => setDerivedTitle(extractH1(c))}
          />
        </main>
      </div>

      <InlineDrawer open={infoOpen} onClose={() => setInfoOpen(false)} title="Document information">
        <dl className={styles.metaList}>
          {paramTitle && <MetaItem label="Title" value={paramTitle} />}
          {paramFile && <MetaItem label="File" value={paramFile} />}
          {paramAuthor && <MetaItem label="Author" value={paramAuthor} />}
          {paramRepo && <MetaItem label="Repository" value={paramRepo} />}
          <MetaItem label="UID" value={uid} />
        </dl>
      </InlineDrawer>
    </div>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metaItem}>
      <dt className={styles.metaLabel}>{label}</dt>
      <dd className={styles.metaValue}>{value}</dd>
    </div>
  );
}
