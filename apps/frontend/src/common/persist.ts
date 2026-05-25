// src/utils/persist.ts
export const NS = "fred";
const key = (name: string) => `${NS}:${name}`;

export function load<T>(name: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key(name));
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function save<T>(name: string, value: T): void {
  try {
    localStorage.setItem(key(name), JSON.stringify(value));
  } catch {
    /* no-op */
  }
}

/**
 * Merge a partial value into a single entry of a string-keyed map in localStorage.
 * V is the value type stored in the map, e.g., AgentPrefs or SessionMeta.
 */
export function updateMap<V extends object>(name: string, mapKey: string, patch: Partial<V>): Record<string, V> {
  const map = load<Record<string, V>>(name, {} as Record<string, V>);
  const prev = (map[mapKey] ?? {}) as V;
  const next: Record<string, V> = {
    ...map,
    [mapKey]: { ...(prev as object), ...(patch as object) } as V,
  };
  save(name, next);
  return next;
}

/**
 * Rename a key in a string-keyed map in localStorage.
 * If newKey already exists, this will not overwrite it.
 */
export function renameKeyInMap<V>(name: string, oldKey: string, newKey: string): Record<string, V> {
  const map = load<Record<string, V>>(name, {} as Record<string, V>);
  if (oldKey !== newKey && map[oldKey] && !map[newKey]) {
    map[newKey] = map[oldKey];
  }
  delete map[oldKey];
  save(name, map);
  return map;
}
