import { SvgIcon, SvgIconProps } from "@mui/material";
import { useEffect, useState } from "react";

interface DynamicSvgIconProps extends Omit<SvgIconProps, "component"> {
  /**
   * The path to the SVG file relative to the public directory
   * Example: "images/icon_lumi.svg" or "images/icon_lumi_dark.svg"
   */
  iconPath: string;
}

/**
 * A component that dynamically imports and renders SVG files with Material-UI theme support.
 * The SVG content is fetched and rendered inside a SvgIcon component, allowing it to inherit
 * theme colors like "action", "primary", etc.
 */
export function DynamicSvgIcon({ iconPath, ...svgIconProps }: DynamicSvgIconProps) {
  const [svgContent, setSvgContent] = useState<string | null>(null);
  const [error, setError] = useState<boolean>(false);

  useEffect(() => {
    const loadSvg = async () => {
      try {
        // Fetch the SVG file from the public directory
        const response = await fetch(`/${iconPath}`);
        if (!response.ok) {
          throw new Error(`Failed to load SVG: ${response.statusText}`);
        }
        const svgText = await response.text();
        setSvgContent(svgText);
        setError(false);
      } catch (err) {
        console.error(`Error loading SVG from ${iconPath}:`, err);
        setError(true);
      }
    };

    loadSvg();
  }, [iconPath]);

  if (error || !svgContent) {
    // Return empty SvgIcon if loading or error
    return <SvgIcon {...svgIconProps} />;
  }

  // Parse the SVG content to extract the viewBox and inner content
  const parser = new DOMParser();
  const svgDoc = parser.parseFromString(svgContent, "image/svg+xml");
  const svgElement = svgDoc.querySelector("svg");

  if (!svgElement) {
    return <SvgIcon {...svgIconProps} />;
  }

  // Extract viewBox attribute
  const viewBox = svgElement.getAttribute("viewBox") || "0 0 24 24";

  // Extract all child elements as string
  const innerHTML = svgElement.innerHTML;

  return (
    <SvgIcon {...svgIconProps} viewBox={viewBox}>
      <g dangerouslySetInnerHTML={{ __html: innerHTML }} />
    </SvgIcon>
  );
}
