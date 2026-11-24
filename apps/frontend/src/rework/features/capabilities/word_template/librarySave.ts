// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import type {
  Library,
  LibraryChange,
  PowerPointFile,
  UploadWordTemplateApiArg,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import type { TemplateLibraryEntryDraft } from "./templateLibrary";

export function libraryEntries(library: Library | undefined): TemplateLibraryEntryDraft[] {
  return (library?.files ?? []).map(({ file, label }) => ({
    template_key: file.id,
    label,
    filename: file.name,
    slot: file.slot,
  }));
}

/** Stage CP receipts; the caller accepts them with the agent/configuration transaction. */
export async function stageWordLibrary({
  spaceId,
  runtimeId,
  agentInstanceId,
  templateId,
  entries,
  files,
  previous,
  upload,
}: {
  spaceId: string;
  runtimeId: string;
  agentInstanceId?: string;
  templateId?: string;
  upload: (arg: UploadWordTemplateApiArg) => Promise<PowerPointFile>;
  entries: TemplateLibraryEntryDraft[];
  files: File[];
  previous: Library | undefined;
}): Promise<LibraryChange> {
  const own = previous?.source === "agent" || !agentInstanceId ? (previous?.files ?? []) : [];
  const retained = new Set(entries.flatMap((entry) => (entry.template_key ? [entry.template_key] : [])));
  const slots = new Set(own.filter(({ file }) => retained.has(file.id)).map(({ file }) => file.slot));
  const pending = [...files];
  const accepted: LibraryChange["files"] = [];
  for (const entry of entries) {
    if (entry.template_key) {
      accepted.push({ file_id: entry.template_key, label: entry.label });
      continue;
    }
    const file = pending.shift();
    if (!file) throw new Error("Word template upload is missing");
    const slot = Array.from({ length: 8 }, (_, index) => index).find((index) => !slots.has(index));
    if (slot === undefined) throw new Error("A Word library holds at most eight templates");
    slots.add(slot);
    const old = own.find(({ file: current }) => current.slot === slot);
    const receipt = await upload({
      spaceId,
      runtimeId,
      agentInstanceId,
      templateId,
      slot,
      expectedFileId: old?.file.id,
      "Idempotency-Key": crypto.randomUUID(),
      fileUpload: { file },
    });
    accepted.push({ file_id: receipt.id, label: entry.label });
  }
  if (pending.length) throw new Error("Word template uploads do not match the library");
  return {
    files: accepted,
    expected_file_ids: previous?.source === "agent" || !agentInstanceId ? (previous?.own_file_ids ?? []) : [],
  };
}
