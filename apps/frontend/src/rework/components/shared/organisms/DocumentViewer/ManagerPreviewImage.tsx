// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useAuthToken } from "../../../../../security/AuthContext";
import { KeyCloakService } from "../../../../../security/KeycloakService";
import { handlePlatformAccessResponse } from "../../../../../common/platformAccess";
import styles from "./DocumentViewer.module.css";
import { managerActor } from "../../../../features/imports/managerImportRun";

export function managerImagePath(source?: string): string | null {
  try {
    const path = decodeURIComponent(source ?? "").replace(/^(\.\/)+/, "");
    return path.length > 0 &&
      new TextEncoder().encode(path).length <= 255 &&
      /^[\p{L}\p{N}_. /-]+$/u.test(path) &&
      path.split("/").every((part) => part && part !== "." && part !== "..")
      ? path
      : null;
  } catch {
    return null;
  }
}

/** Only visible, manifest-backed images are loaded; leaving the viewport releases their bytes. */
export function ManagerPreviewImage({ documentUid, src, alt }: { documentUid: string; src?: string; alt?: string }) {
  const token = useAuthToken();
  const ref = useRef<HTMLSpanElement>(null);
  const [visible, setVisible] = useState(false);
  const [loaded, setLoaded] = useState<{ key: string; url: string }>();
  const path = managerImagePath(src);
  const key = `${documentUid}/${path}/${token}`;
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { rootMargin: "200px" });
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!visible || !path || !token) return;
    const controller = new AbortController();
    let url: string | undefined;
    const actor = managerActor();
    const load = async () => {
      await KeyCloakService.ensureFreshToken(30);
      if (actor !== managerActor() || controller.signal.aborted) return;
      const response = await fetch(
        `/control-plane/v1/documents/${encodeURIComponent(documentUid)}/preview?artifact=${encodeURIComponent(path)}`,
        {
          headers: { Authorization: `Bearer ${KeyCloakService.GetToken() ?? ""}` },
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]),
          cache: "no-store",
          redirect: "error",
        },
      );
      await handlePlatformAccessResponse(response);
      const size = Number(response.headers.get("content-length"));
      if (
        !response.ok ||
        size <= 0 ||
        size > 8 * 1024 * 1024 ||
        !/^image\/(png|jpeg|webp|gif)$/.test(response.headers.get("content-type") ?? "")
      ) {
        await response.body?.cancel();
        return;
      }
      const blob = await response.blob();
      if (blob.size !== size || controller.signal.aborted || actor !== managerActor()) return;
      url = URL.createObjectURL(blob);
      setLoaded({ key, url });
    };
    void load().catch(() => {});
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
      setLoaded(undefined);
    };
  }, [visible, path, documentUid, token, key]);
  return (
    <span ref={ref} className={styles.previewImage}>
      {visible && loaded?.key === key ? (
        <img src={loaded.url} alt={alt ?? ""} />
      ) : (
        <span role="img" aria-label={alt}>
          {alt}
        </span>
      )}
    </span>
  );
}
