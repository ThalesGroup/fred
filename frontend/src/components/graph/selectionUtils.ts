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

export const getNodeId = (n: any): string => String(n?.name ?? n?.id ?? "");

export const isAdditiveEvent = (ev: MouseEvent): boolean =>
  !!(ev.shiftKey || ev.ctrlKey || (ev as any).metaKey);

// Create a position key function with given precision for overlap grouping
export const makePosKey = (overlapPrecision: number) => {
  return (n: any): string => {
    const pow = Math.pow(10, overlapPrecision);
    const rx = Math.round((n.x ?? n.fx ?? 0) * pow) / pow;
    const ry = Math.round((n.y ?? n.fy ?? 0) * pow) / pow;
    const rz = Math.round((n.z ?? n.fz ?? 0) * pow) / pow;
    return `${rx}|${ry}|${rz}`;
  };
};

// Build a map from position key to array of node ids for fast lookup of overlaps
export const buildOverlapMap = (nodes: any[], posKey: (n: any) => string): Map<string, string[]> => {
  const m = new Map<string, string[]>();
  for (const n of nodes) {
    const k = posKey(n);
    const id = String((n as any).name ?? (n as any).id);
    if (!m.has(k)) m.set(k, []);
    m.get(k)!.push(id);
  }
  return m;
};
