import { useEffect, useRef } from "react";

export interface SessionChangeCallbacks {
  /** Called on any session change (including draft ↔ session transitions) */
  onChange?: (prev: string | undefined, curr: string | undefined) => void;
  /** Called when transitioning from draft to a session (e.g., clicking existing conversation or first message creating session) */
  onDraftToSession?: (sessionId: string) => void;
  /** Called when transitioning from a session back to draft (e.g., clicking "new conversation") */
  onSessionToDraft?: (prevSessionId: string) => void;
  /** Called when switching between two different existing sessions (e.g., clicking different conversation in sidebar) */
  onSessionSwitch?: (prevSessionId: string, newSessionId: string) => void;
}

/**
 * Hook to detect and react to session ID changes.
 *
 * Useful for handling state cleanup, resetting UI, or performing side effects
 * when navigating between conversations (draft ↔ sessions).
 *
 * @param sessionId - Current session ID (undefined for draft/new conversations)
 * @param callbacks - Callbacks for different transition types
 *
 * @example
 * ```tsx
 * useSessionChange(sessionId, {
 *   onChange: (prev, curr) => console.log('Session changed:', prev, '->', curr),
 *   onDraftToSession: (id) => console.log('Navigated to session:', id),
 *   onSessionToDraft: (prevId) => console.log('Returned to draft from:', prevId),
 *   onSessionSwitch: (prevId, newId) => console.log('Switched sessions:', prevId, '->', newId),
 * });
 * ```
 */
export function useSessionChange(sessionId: string | undefined, callbacks: SessionChangeCallbacks) {
  const prevSessionIdRef = useRef<string | undefined>(sessionId);
  const isInitialMount = useRef(true);

  useEffect(() => {
    const prev = prevSessionIdRef.current;
    const curr = sessionId;

    // Skip callbacks on initial mount
    if (isInitialMount.current) {
      isInitialMount.current = false;
      prevSessionIdRef.current = curr;
      return;
    }

    // No change
    if (prev === curr) {
      return;
    }

    // Call the generic onChange callback
    callbacks.onChange?.(prev, curr);

    // Detect specific transition types
    if (!prev && curr) {
      // Draft → Session (navigating to existing conversation or first message creating one)
      callbacks.onDraftToSession?.(curr);
    } else if (prev && !curr) {
      // Session → Draft (new conversation button clicked)
      callbacks.onSessionToDraft?.(prev);
    } else if (prev && curr) {
      // Session → Different Session (switching between conversations)
      callbacks.onSessionSwitch?.(prev, curr);
    }

    prevSessionIdRef.current = curr;
  }, [sessionId, callbacks]);
}
