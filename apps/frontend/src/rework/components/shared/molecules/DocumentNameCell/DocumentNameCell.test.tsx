// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import type { Document } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { presentManagerDocument } from "../../../../features/imports/managerDocuments";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

import DocumentNameCell from "./DocumentNameCell";

const managerDocument = (name: string, mime: string): Document => ({
  id: "doc",
  space_id: "team",
  folder_id: null,
  name,
  mime,
  size: 355,
  sha256: "sha",
  created_at: "2026-11-12T07:27:00Z",
  created_by: "bob",
  retrievable: true,
  retrievable_pending: false,
});

it("pictures a manager document by its file name, not by the browser's media type", () => {
  const markup = renderToStaticMarkup(
    <DocumentNameCell
      doc={presentManagerDocument(managerDocument("07-staffing-plan.csv", "application/octet-stream"))}
    />,
  );
  expect(markup).toContain(">table<");
  expect(markup).toContain("var(--success)");
});
