// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useEffect } from "react";
import { useDispatch } from "react-redux";
import { useMountSessionId } from "../useOpenSessionId";
import type { UiPartRendererProps } from "../types";
import type { WritableDocumentPartData } from "./types";
import { upsertFromPart } from "./writableDocumentSlice";

/** Live/history snapshots feed the editor and Files drawer without a duplicate card. */
export function WritableDocumentCardRenderer({ part }: UiPartRendererProps) {
  const dispatch = useDispatch();
  const sessionId = useMountSessionId();
  const doc = part as unknown as WritableDocumentPartData;
  useEffect(() => {
    if (sessionId) dispatch(upsertFromPart({ sessionId, doc }));
  }, [sessionId, doc, dispatch]);
  return null;
}
