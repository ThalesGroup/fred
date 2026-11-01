// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { createContext, useCallback, useContext, useMemo, useRef, useState, type PropsWithChildren } from "react";
import { useLocalStorageState } from "../../../hooks/useLocalStorageState";

interface ChatNavPanel {
  collapsed: boolean;
  toggle: () => void;
}

interface ChatNavRoom {
  /** Folds the panel for a viewer that needs the room; returns the width gained. */
  makeRoom: (chatBodyWidth: number) => number;
  releaseRoom: () => void;
}

// Mirrors the panel's CSS width. A viewer takes half of the chat body, so below
// this body width the chat would keep less than 600px of it.
const NAV_PANEL_WIDTH = 254;
const MIN_BODY_WIDTH_BESIDE_VIEWER = 1200;

const ChatNavPanelContext = createContext<ChatNavPanel>({ collapsed: false, toggle: () => {} });
// Stable on its own so that an open viewer does not re-render on each toggle.
const ChatNavRoomContext = createContext<ChatNavRoom>({ makeRoom: () => 0, releaseRoom: () => {} });

/** The toggle only exists on the chat page, so collapsing never applies elsewhere. */
export const isChatRoute = (pathname: string) => pathname.includes("/managed-chat/");

export function ChatNavPanelProvider({ children }: PropsWithChildren) {
  const [folded, setFolded] = useLocalStorageState("chat-nav-panel-collapsed", false);
  // Never persisted: only the user's own choice survives a reload.
  const [foldedForViewer, setFoldedForViewer] = useState(false);
  const collapsed = folded || foldedForViewer;
  const collapsedRef = useRef(collapsed);
  collapsedRef.current = collapsed;
  const makeRoom = useCallback((chatBodyWidth: number) => {
    if (collapsedRef.current || chatBodyWidth >= MIN_BODY_WIDTH_BESIDE_VIEWER) return 0;
    setFoldedForViewer(true);
    return NAV_PANEL_WIDTH;
  }, []);
  const releaseRoom = useCallback(() => setFoldedForViewer(false), []);
  const room = useMemo(() => ({ makeRoom, releaseRoom }), [makeRoom, releaseRoom]);
  const value = useMemo(
    () => ({
      collapsed,
      toggle: () => (foldedForViewer ? setFoldedForViewer(false) : setFolded((current) => !current)),
    }),
    [collapsed, foldedForViewer, setFolded],
  );
  return (
    <ChatNavRoomContext.Provider value={room}>
      <ChatNavPanelContext.Provider value={value}>{children}</ChatNavPanelContext.Provider>
    </ChatNavRoomContext.Provider>
  );
}

export const useChatNavPanel = () => useContext(ChatNavPanelContext);
export const useChatNavRoom = () => useContext(ChatNavRoomContext);
