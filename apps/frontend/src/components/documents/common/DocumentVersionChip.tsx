import { Chip } from "@mui/material";
import React from "react";

type VersionChipProps = {
  version?: number | null;
  size?: "small" | "medium";
};

/**
 * Small reusable badge to surface document version (1-based for display).
 * Renders nothing when version is falsy or 0 (base version).
 */
export const DocumentVersionChip: React.FC<VersionChipProps> = ({ version, size = "small" }) => {
  if (!version || version <= 0) return null;
  return (
    <Chip
      label={`v${version + 1}`}
      size={size}
      color="warning"
      variant="outlined"
      sx={{ ml: 0.5, height: size === "small" ? 18 : undefined, fontSize: size === "small" ? "0.7rem" : undefined }}
    />
  );
};

/** Helper to read version off known shapes (DocumentMetadata.identity.version or flat version) */
export const extractDocumentVersion = (doc: any): number | undefined => {
  if (!doc) return undefined;
  if (typeof doc.version === "number") return doc.version;
  if (doc.identity && typeof doc.identity.version === "number") return doc.identity.version;
  return undefined;
};
