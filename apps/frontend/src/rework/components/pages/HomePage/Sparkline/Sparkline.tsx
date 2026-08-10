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

interface SparklineProps {
  /** Series to plot, oldest → newest. Rendered as a small trend line. */
  values: number[];
  /** Stroke/fill color (a CSS color or a `var(--token)`). */
  color: string;
  width?: number;
  height?: number;
  /** Faint area fill under the line. */
  fill?: boolean;
}

/** Minimal, dependency-free trend line for compact stat tiles. Purely
 * decorative — flagged `aria-hidden`; the number it accompanies carries the
 * meaning. */
export default function Sparkline({ values, color, width = 74, height = 26, fill = false }: SparklineProps) {
  if (values.length < 2) return null;
  const pad = 3;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = (width - pad * 2) / (values.length - 1);
  const points = values.map((v, i) => {
    const x = pad + i * stepX;
    const y = pad + (1 - (v - min) / span) * (height - pad * 2);
    return [x, y] as const;
  });
  const line = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const [lastX, lastY] = points[points.length - 1];
  const area = `${line} ${(width - pad).toFixed(1)},${height} ${pad},${height}`;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      {fill && <polygon points={area} fill={color} opacity="0.1" />}
      <polyline
        points={line}
        fill="none"
        stroke={color}
        strokeWidth="1.8"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={lastX} cy={lastY} r="2.4" fill={color} />
    </svg>
  );
}
