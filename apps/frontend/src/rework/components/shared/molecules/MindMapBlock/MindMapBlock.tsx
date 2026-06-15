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

import { useEffect, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import { useIsDark } from "../../../../core/hooks/useIsDark";
import styles from "./MindMapBlock.module.css";
import {
  escapeHtml,
  findNodeById,
  findPathToNode,
  parseMindMapPayload,
  type MindMapNode,
  type MindMapPayload,
} from "./mindmapParser";

interface MindMapBlockProps {
  code: string;
  language?: string;
}

type MindMapTheme = {
  tooltipBackground: string;
  tooltipBorder: string;
  tooltipText: string;
  lineColor: string;
  nodeColor: string;
  nodeBorder: string;
  labelColor: string;
  labelBackground: string;
  emphasisNodeColor: string;
  emphasisNodeBorder: string;
  emphasisLabelColor: string;
  emphasisLabelBackground: string;
  nodeSize: number;
  labelFontSize: number;
  labelRadius: number;
  labelPaddingBlock: number;
  labelPaddingInline: number;
  nodeBorderWidth: number;
  emphasisBorderWidth: number;
};

export type MindMapChartOption = {
  backgroundColor: string;
  tooltip: {
    trigger: string;
    triggerOn: string;
    formatter: (params: { data?: { name?: string; summary?: string; detail?: string } }) => string;
    backgroundColor: string;
    borderColor: string;
    textStyle: { color: string };
  };
  series: Array<Record<string, unknown>>;
};

function chartNode(node: MindMapNode): Record<string, unknown> {
  return {
    id: node.id,
    name: node.name,
    value: node.summary ?? "",
    summary: node.summary ?? "",
    detail: node.detail ?? "",
    evidence: node.evidence ?? [],
    children: (node.children ?? []).map(chartNode),
  };
}

// ECharts needs resolved color strings and numeric lengths rather than CSS var references.
function readCssVar(source: HTMLElement, name: string): string {
  return getComputedStyle(source).getPropertyValue(name).trim();
}

// Converts a token-backed CSS length into pixels for chart fields such as fontSize and padding.
function resolveTokenLengthPx(source: HTMLElement, name: string): number {
  const value = readCssVar(source, name);
  if (value.endsWith("px")) {
    return Number.parseFloat(value);
  }
  if (value.endsWith("rem")) {
    const rootFontSize = Number.parseFloat(getComputedStyle(document.documentElement).fontSize);
    return Number.parseFloat(value) * rootFontSize;
  }
  return Number.parseFloat(value) || 0;
}

function resolveFontSizePx(source: HTMLElement, name: string): number {
  const value = readCssVar(source, name);
  const match = value.match(/\s([0-9.]+(?:px|rem))\s*\/?/);
  if (!match) return 0;

  const fontSize = match[1];
  if (fontSize.endsWith("px")) {
    return Number.parseFloat(fontSize);
  }
  if (fontSize.endsWith("rem")) {
    const rootFontSize = Number.parseFloat(getComputedStyle(document.documentElement).fontSize);
    return Number.parseFloat(fontSize) * rootFontSize;
  }
  return Number.parseFloat(fontSize) || 0;
}

function buildMindMapTheme(source: HTMLElement): MindMapTheme {
  const tooltipBackground = readCssVar(source, "--surface-container-highest");
  const tooltipBorder = readCssVar(source, "--outline-variant");
  const tooltipText = readCssVar(source, "--on-surface");
  const nodeSize = resolveTokenLengthPx(source, "--spacing-s");
  const labelFontSize = resolveFontSizePx(source, "--font-label-small");
  const labelRadius = resolveTokenLengthPx(source, "--radius-xs");
  const labelPaddingBlock = resolveTokenLengthPx(source, "--spacing-3xs");
  const labelPaddingInline = resolveTokenLengthPx(source, "--spacing-xs");
  const nodeBorderWidth = Math.max(1, resolveTokenLengthPx(source, "--spacing-3xs") / 2);
  const emphasisBorderWidth = Math.max(2, resolveTokenLengthPx(source, "--spacing-3xs"));

  return {
    tooltipBackground,
    tooltipBorder,
    tooltipText,
    lineColor: readCssVar(source, "--outline"),
    nodeColor: readCssVar(source, "--primary"),
    nodeBorder: readCssVar(source, "--primary-container"),
    labelColor: readCssVar(source, "--on-surface"),
    labelBackground: readCssVar(source, "--surface-container-high"),
    emphasisNodeColor: readCssVar(source, "--warning"),
    emphasisNodeBorder: readCssVar(source, "--warning-container"),
    emphasisLabelColor: readCssVar(source, "--on-warning-container"),
    emphasisLabelBackground: readCssVar(source, "--warning-container"),
    nodeSize,
    labelFontSize,
    labelRadius,
    labelPaddingBlock,
    labelPaddingInline,
    nodeBorderWidth,
    emphasisBorderWidth,
  };
}

export function buildMindMapChartOption(
  payload: MindMapPayload,
  theme: MindMapTheme,
): MindMapChartOption {
  const initialDepth = Math.max(1, Math.min(payload.presentation?.initialDepth ?? 2, 6));
  const isRadial = payload.presentation?.layout === "radial";

  return {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      triggerOn: "mousemove",
      formatter: (params: { data?: { name?: string; summary?: string; detail?: string } }) => {
        const name = escapeHtml(params.data?.name ?? "Topic");
        const summary = escapeHtml(params.data?.summary ?? "");
        const detail = escapeHtml(params.data?.detail ?? "");
        const parts = [`<strong>${name}</strong>`];
        if (summary) parts.push(`<div>${summary}</div>`);
        if (detail) parts.push(`<div>${detail}</div>`);
        return parts.join("");
      },
      backgroundColor: theme.tooltipBackground,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.tooltipText },
    },
    series: [
      {
        type: "tree",
        data: [chartNode(payload.root)],
        top: "6%",
        left: "10%",
        bottom: "6%",
        right: "18%",
        symbol: "circle",
        symbolSize: theme.nodeSize,
        roam: true,
        expandAndCollapse: true,
        initialTreeDepth: initialDepth,
        layout: isRadial ? "radial" : "orthogonal",
        orient: "LR",
        animationDuration: 350,
        animationDurationUpdate: 450,
        lineStyle: {
          color: theme.lineColor,
          width: theme.nodeBorderWidth,
          curveness: 0.35,
        },
        itemStyle: {
          color: theme.nodeColor,
          borderColor: theme.nodeBorder,
          borderWidth: theme.nodeBorderWidth,
        },
        label: {
          position: "left",
          verticalAlign: "middle",
          align: "right",
          color: theme.labelColor,
          fontSize: theme.labelFontSize,
          backgroundColor: theme.labelBackground,
          borderRadius: theme.labelRadius,
          padding: [theme.labelPaddingBlock, theme.labelPaddingInline],
        },
        leaves: {
          label: {
            position: "right",
            verticalAlign: "middle",
            align: "left",
          },
        },
        emphasis: {
          focus: "none",
          itemStyle: {
            color: theme.emphasisNodeColor,
            borderColor: theme.emphasisNodeBorder,
            borderWidth: theme.emphasisBorderWidth,
          },
          label: {
            color: theme.emphasisLabelColor,
            fontWeight: 700,
            backgroundColor: theme.emphasisLabelBackground,
            borderRadius: theme.labelRadius,
            padding: [theme.labelPaddingBlock, theme.labelPaddingInline],
          },
        },
      },
    ],
  };
}

export function MindMapBlock({ code, language = "mindmap-json" }: MindMapBlockProps) {
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const isDark = useIsDark();
  const parsed = useMemo(() => parseMindMapPayload(code), [code]);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ReactECharts | null>(null);
  const highlightedNameRef = useRef<string | null>(null);
  const [chartReady, setChartReady] = useState(false);
  const theme = useMemo(() => buildMindMapTheme(rootRef.current ?? document.documentElement), [isDark]);

  const rootId = parsed.ok ? parsed.payload.root.id : "";
  const [selectedNodeId, setSelectedNodeId] = useState(rootId);

  useEffect(() => {
    if (parsed.ok) {
      setSelectedNodeId(parsed.payload.root.id);
    }
  }, [parsed]);

  useEffect(() => {
    setChartReady(false);
    highlightedNameRef.current = null;
  }, [code]);

  useEffect(() => {
    if (!parsed.ok || !chartReady) return;
    const instance = chartRef.current?.getEchartsInstance();
    if (!instance) return;

    const selectedNode = findNodeById(parsed.payload.root, selectedNodeId) ?? parsed.payload.root;
    const frameId = requestAnimationFrame(() => {
      try {
        if (highlightedNameRef.current) {
          instance.dispatchAction({
            type: "downplay",
            seriesIndex: 0,
            name: highlightedNameRef.current,
          });
        }

        highlightedNameRef.current = selectedNode.name;
        instance.dispatchAction({
          type: "highlight",
          seriesIndex: 0,
          name: selectedNode.name,
        });
      } catch {
        // ECharts can still be mid-initialization immediately after a refresh.
      }
    });

    return () => cancelAnimationFrame(frameId);
  }, [chartReady, parsed, selectedNodeId]);

  function handleCopy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  if (parsed.ok === false) {
    return (
      <div className={styles.block}>
        <div className={styles.header}>
          <span className={styles.lang}>{language}</span>
          <button className={styles.copy} onClick={handleCopy} aria-label="Copy mindmap JSON">
            {copied ? "✓ Copied" : "Copy"}
          </button>
        </div>
        <div className={styles.error}>
          <span className={styles.errorLabel}>Mindmap could not be rendered</span>
          <p className={styles.errorText}>{parsed.error}</p>
          <details className={styles.rawDetails}>
            <summary>Show raw payload</summary>
            <pre className={styles.rawCode}>{parsed.raw}</pre>
          </details>
        </div>
      </div>
    );
  }

  const payload = parsed.payload;
  const selectedNode = findNodeById(payload.root, selectedNodeId) ?? payload.root;
  const breadcrumb = findPathToNode(payload.root, selectedNode.id) ?? [payload.root];

  const option = useMemo(() => buildMindMapChartOption(payload, theme), [payload, theme]);

  return (
    <div ref={rootRef} className={`${styles.block} ${expanded ? styles.expanded : ""}`}>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <span className={styles.lang}>{language}</span>
          <strong className={styles.title}>{payload.title}</strong>
        </div>
        <div className={styles.actions}>
          <button className={styles.action} onClick={() => setSelectedNodeId(payload.root.id)}>
            Reset
          </button>
          <button className={styles.action} onClick={() => setExpanded((value) => !value)}>
            {expanded ? "Collapse" : "Expand"}
          </button>
          <button className={styles.copy} onClick={handleCopy} aria-label="Copy mindmap JSON">
            {copied ? "✓ Copied" : "Copy"}
          </button>
        </div>
      </div>

      <div className={styles.summaryBar}>
        <div className={styles.breadcrumbs}>
          {breadcrumb.map((node, index) => (
            <button key={node.id} className={styles.crumb} onClick={() => setSelectedNodeId(node.id)}>
              {index > 0 ? " / " : ""}
              {node.name}
            </button>
          ))}
        </div>
        <p className={styles.summary}>Selected: {selectedNode.name}</p>
        {payload.summary ? <p className={styles.summary}>{payload.summary}</p> : null}
      </div>

      <div className={styles.content}>
        <div className={styles.chartPane}>
          <ReactECharts
            ref={chartRef}
            className={styles.chart}
            option={option}
            notMerge
            lazyUpdate
            onChartReady={() => setChartReady(true)}
            onEvents={{
              click: (params: { data?: { id?: string } }) => {
                const id = params.data?.id;
                if (!id) return;
                setSelectedNodeId(id);
              },
            }}
          />
        </div>
      </div>
    </div>
  );
}
