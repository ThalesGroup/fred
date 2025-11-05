import { Dispatch, SetStateAction, useCallback, useEffect, useMemo, useRef, useState } from "react";

type Initializer<T> = T | (() => T);

const isBrowser = typeof window !== "undefined" && typeof window.localStorage !== "undefined";

const resolveInitializer = <T>(value: Initializer<T>): T =>
  typeof value === "function" ? (value as () => T)() : value;
const resolveUpdater = <T>(value: SetStateAction<T>, previous: T): T =>
  typeof value === "function" ? (value as (prevState: T) => T)(previous) : value;

// Read and parse the stored value; return undefined when no entry or on failure.
function readFromStorage<T>(key: string): T | undefined {
  if (!isBrowser) {
    return undefined;
  }

  try {
    const raw = window.localStorage.getItem(key);
    if (raw !== null) {
      return JSON.parse(raw) as T;
    }
  } catch (error) {
    console.warn(`useLocalStorageState: failed to read key "${key}" from localStorage`, error);
  }

  return undefined;
}

// Persist the latest state snapshot, dropping the entry when the value is undefined.
function writeToStorage<T>(key: string, value: T): void {
  if (!isBrowser) return;

  if (value === undefined) {
    window.localStorage.removeItem(key);
    return;
  }

  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.warn(`useLocalStorageState: failed to write key "${key}" to localStorage`, error);
  }
}

// React state hook with a localStorage backing so values survive reloads and stay in sync across tabs.
export function useLocalStorageState<T>(key: string, initialValue: Initializer<T>): [T, Dispatch<SetStateAction<T>>] {
  const initialValueRef = useRef<Initializer<T>>(initialValue);

  // Keep the latest initializer so storage resets mirror updated defaults.
  useEffect(() => {
    initialValueRef.current = initialValue;
  }, [initialValue]);

  const storageKey = useMemo(() => `localHook:${key}`, [key]);

  const readValue = useCallback(() => {
    const storedValue = readFromStorage<T>(storageKey);
    return storedValue === undefined ? resolveInitializer(initialValueRef.current) : storedValue;
  }, [storageKey]);

  // Real useState with init value potentialy coming from localStorage
  const [value, setValue] = useState<T>(() => readValue());

  // Re-sync when the key changes (e.g., dynamic storage keys).
  useEffect(() => {
    setValue(readValue());
  }, [readValue]);

  // Listen for localStorage events from other tabs/windows and refresh the state.
  useEffect(() => {
    if (!isBrowser) return;

    const handleStorage = (event: StorageEvent) => {
      if (event.storageArea !== window.localStorage || event.key !== storageKey) return;

      if (event.newValue === null) {
        setValue(resolveInitializer(initialValueRef.current));
        return;
      }

      try {
        setValue(JSON.parse(event.newValue) as T);
      } catch (error) {
        console.warn(`useLocalStorageState: failed to parse storage event for key "${storageKey}"`, error);
        setValue(resolveInitializer(initialValueRef.current));
      }
    };

    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, [storageKey]);

  // Setter that mirror useState semantics while persisting the new value to localStorage.
  const setStoredValue: Dispatch<SetStateAction<T>> = useCallback(
    (updater) => {
      setValue((previous) => {
        const nextValue = resolveUpdater(updater, previous);
        writeToStorage(storageKey, nextValue);
        return nextValue;
      });
    },
    [storageKey],
  );

  return useMemo(() => [value, setStoredValue], [setStoredValue, value]);
}
