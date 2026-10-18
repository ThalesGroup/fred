// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0

import { useSyncExternalStore } from "react";
import type { Store, UnknownAction } from "@reduxjs/toolkit";
import type { ThunkDispatch } from "redux-thunk";
import { runtimeApi, type ConversationFileResponse } from "../../../slices/runtime/runtimeOpenApi";
import type { ConversationFileRootState } from "./conversationFileSlice";

type EditorStore = Store<ConversationFileRootState> & {
  dispatch: ThunkDispatch<ConversationFileRootState, unknown, UnknownAction>;
};
type FileIdentity = { sessionId: string; teamId: string; path: string };
export interface FileDraft {
  content: string;
  savedContent: string;
  editable: boolean;
  saving: boolean;
  failed: boolean;
  version: number;
  saveRevision: number;
}
type Entry = FileIdentity & {
  draft: FileDraft;
  timer?: ReturnType<typeof setTimeout>;
  pending?: Promise<void>;
};
const keyOf = ({ sessionId, teamId, path }: FileIdentity) => JSON.stringify([sessionId, teamId, path]);
const coordinators = new WeakMap<object, ConversationEditors>();
const active = new Set<ConversationEditors>();

/** Browser/store-local drafts survive panel remounts and refreshes, never enter model context. */
export class ConversationEditors {
  private entries = new Map<string, Entry>();
  private listeners = new Set<() => void>();
  constructor(private store: EditorStore) {}
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private update(entry: Entry, patch: Partial<FileDraft>) {
    entry.draft = { ...entry.draft, ...patch };
    this.listeners.forEach((listener) => listener());
  }
  get(identity: FileIdentity) {
    return this.entries.get(keyOf(identity))?.draft;
  }
  accept(identity: FileIdentity, file: ConversationFileResponse) {
    const key = keyOf(identity);
    const entry = this.entries.get(key);
    if (!entry) {
      this.entries.set(key, {
        ...identity,
        draft: {
          content: file.content,
          savedContent: file.content,
          editable: file.editable,
          saving: false,
          failed: false,
          version: 0,
          saveRevision: 0,
        },
      });
      this.listeners.forEach((listener) => listener());
    } else if (!this.dirty(entry) && !entry.pending) {
      this.update(entry, { content: file.content, savedContent: file.content, editable: file.editable });
    } else if (entry.draft.editable !== file.editable) {
      this.update(entry, { editable: file.editable });
    }
  }
  private dirty(entry: Entry) {
    return entry.draft.content !== entry.draft.savedContent;
  }
  change(identity: FileIdentity, content: string) {
    const entry = this.entries.get(keyOf(identity));
    if (!entry?.draft.editable) return;
    this.update(entry, { content, version: entry.draft.version + 1, failed: false });
    clearTimeout(entry.timer);
    entry.timer = setTimeout(() => {
      void this.save(entry).catch(() => undefined);
    }, 600);
  }
  private async save(entry: Entry): Promise<void> {
    clearTimeout(entry.timer);
    if (entry.pending) {
      await entry.pending;
      return this.save(entry);
    }
    if (!this.dirty(entry)) return;
    if (!entry.draft.editable) {
      this.update(entry, { failed: true });
      throw new Error("Conversation file is read-only");
    }
    const content = entry.draft.content;
    this.update(entry, { saving: true, failed: false });
    const request = this.store.dispatch(
      runtimeApi.endpoints.saveConversationFile.initiate({
        sessionId: entry.sessionId,
        teamId: entry.teamId,
        path: entry.path,
        conversationFileSaveRequest: { content },
      }),
    );
    entry.pending = (async () => {
      try {
        await request.unwrap();
        // Only acknowledge the buffer sent, even if the user typed meanwhile.
        this.update(entry, { savedContent: content, saving: false, saveRevision: entry.draft.saveRevision + 1 });
      } catch (error) {
        this.update(entry, { saving: false, failed: true });
        throw error;
      } finally {
        request.reset();
        entry.pending = undefined;
      }
    })();
    return entry.pending;
  }
  async flush(sessionId: string): Promise<void> {
    // Repeat after awaiting: another editor or keystroke can become dirty in flight.
    while (true) {
      const dirty = [...this.entries.values()].filter(
        (entry) => entry.sessionId === sessionId && (this.dirty(entry) || entry.pending),
      );
      if (!dirty.length) return;
      await Promise.all(dirty.map((entry) => this.save(entry)));
    }
  }
}
export function conversationEditorsFor(store: EditorStore): ConversationEditors {
  let coordinator = coordinators.get(store);
  if (!coordinator) {
    coordinator = new ConversationEditors(store);
    coordinators.set(store, coordinator);
  }
  return coordinator;
}
export function registerConversationEditors(coordinator: ConversationEditors) {
  active.add(coordinator);
  return () => {
    active.delete(coordinator);
  };
}
export async function flushConversationEditors(sessionId: string): Promise<void> {
  await Promise.all([...active].map((coordinator) => coordinator.flush(sessionId)));
}
export function useConversationFileDraft(coordinator: ConversationEditors, identity: FileIdentity) {
  return useSyncExternalStore(coordinator.subscribe, () => coordinator.get(identity));
}
