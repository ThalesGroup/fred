// @vitest-environment happy-dom
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

// The dialog words the tool's note codes with the real fr/en strings: a
// missing key or a raw code on screen fails here, not in front of a user.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import i18next, { type i18n as I18n } from "i18next";
import { afterEach, describe, expect, it, vi } from "vitest";
import en from "../../../../locales/en/translation.json";
import fr from "../../../../locales/fr/translation.json";
import type { BuiltSlide } from "./types";

const i18n = vi.hoisted(() => ({ current: null as I18n | null }));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: i18n.current!.t.bind(i18n.current), i18n: i18n.current }),
}));

const { default: DeckSummaryButton } = await import("./DeckSummaryButton");

const summary: BuiltSlide[] = [
  { number: 1, part: 1, parts: 1, title: "Kick-off", kind: "cover", template: "Cover", notes: [] },
  {
    number: 2,
    part: 1,
    parts: 2,
    title: "Agenda (1/2)",
    kind: "agenda",
    template: "SOMMAIRE",
    notes: [{ code: "list_continued" }],
  },
  {
    number: 2,
    part: 2,
    parts: 2,
    title: "Agenda (2/2)",
    kind: "agenda",
    template: "SOMMAIRE",
    notes: [{ code: "list_continued" }],
  },
  {
    number: 3,
    part: 1,
    parts: 1,
    title: "",
    kind: "bullets",
    template: "Planche à puces",
    notes: [
      { code: "other_kind", kind: "timeline" },
      { code: "text_shortened" },
      { code: "image_unusable", count: 2 },
      { code: "some_future_code" },
    ],
  },
];

let root: Root | null = null;

async function mount(lng: "en" | "fr", data: BuiltSlide[] | null | undefined): Promise<HTMLElement> {
  const instance = i18next.createInstance();
  await instance.init({ lng, resources: { en: { translation: en }, fr: { translation: fr } } });
  i18n.current = instance;
  const container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<DeckSummaryButton summary={data} />));
  return container;
}

function open(container: HTMLElement): HTMLElement {
  act(() => container.querySelector("button")!.click());
  return document.querySelector('[role="dialog"]') as HTMLElement;
}

afterEach(() => {
  act(() => root?.unmount());
  root = null;
  document.body.innerHTML = "";
});

describe("DeckSummaryButton", () => {
  it("is absent without a summary (ppt_filler decks, older parts)", async () => {
    expect((await mount("en", undefined)).querySelector("button")).toBeNull();
    act(() => root?.unmount());
    expect((await mount("en", [])).querySelector("button")).toBeNull();
  });

  it("lists every slide with its kind and plain notes, in English", async () => {
    const container = await mount("en", summary);
    const button = container.querySelector("button")!;
    expect(button.getAttribute("aria-label")).toBe("What was built");
    expect(button.getAttribute("aria-haspopup")).toBe("dialog");
    // The size of the download and close buttons it sits beside.
    expect(button.className).toMatch(/btn-small/);

    const dialog = open(container);
    expect(dialog.textContent).toContain("What was built");
    expect(dialog.textContent).toContain("This presentation has 4 slides.");
    const items = [...dialog.querySelectorAll("ol > li")].map((li) => li.textContent);
    expect(items).toHaveLength(4);
    expect(items[0]).toContain("Kick-off");
    expect(items[0]).toContain("Cover");
    expect(items[1]).toContain("The list continues on the next slide.");
    expect(items[2]).toContain("Continuation of the list from the previous slide.");
    // No title: the template slide's label names it.
    expect(items[3]).toContain("Planche à puces");
    expect(items[3]).toContain("Built as “Bullet points” instead of “Timeline”.");
    expect(items[3]).toContain("Some text was shortened to fit.");
    expect(items[3]).toContain("2 images could not be used.");
    expect(dialog.textContent).not.toContain("some_future_code");
    expect(dialog.textContent).not.toContain("capability.ppt_builder");
  });

  it("speaks French", async () => {
    const container = await mount("fr", summary);
    expect(container.querySelector("button")!.getAttribute("aria-label")).toBe("Ce qui a été construit");
    const dialog = open(container);
    expect(dialog.textContent).toContain("Cette présentation compte 4 diapositives.");
    expect(dialog.textContent).toContain("Sommaire");
    expect(dialog.textContent).toContain("La liste continue sur la diapositive suivante.");
    expect(dialog.textContent).toContain("Construite en « Liste à puces » au lieu de « Frise chronologique ».");
    expect(dialog.textContent).toContain("2 images n'ont pas pu être utilisées.");
    expect(dialog.textContent).not.toContain("capability.ppt_builder");
  });

  it("names a chart built in a content area, a chart type it could not draw and hidden numbers", async () => {
    const charts: BuiltSlide[] = [
      {
        number: 1,
        part: 1,
        parts: 1,
        title: "Revenue",
        kind: "chart",
        template: "Chart",
        notes: [{ code: "chart_type_changed", kind: "radar" }],
      },
      {
        number: 2,
        part: 1,
        parts: 1,
        title: "Headcount",
        kind: "chart",
        template: "Chart",
        notes: [{ code: "chart_shows_shares" }],
      },
      {
        number: 3,
        part: 1,
        parts: 1,
        title: "Shares",
        kind: "bullets",
        template: "Title and Content",
        notes: [{ code: "other_kind", kind: "chart" }],
      },
    ];
    const dialog = open(await mount("fr", charts));
    const items = [...dialog.querySelectorAll("ol > li")].map((li) => li.textContent);
    expect(items[0]).toContain("Graphique");
    expect(items[0]).toContain(
      "Le graphique « radar » n'est pas disponible : les données sont affichées en histogramme.",
    );
    expect(items[2]).toContain("Construite en « Liste à puces » au lieu de « Graphique ».");
    expect(items[1]).toContain("Le graphique affiche des pourcentages : les nombres eux-mêmes ne sont pas affichés.");
  });

  it("words an intent the chart could not show by its field", async () => {
    const slide: BuiltSlide = {
      number: 1,
      part: 1,
      parts: 1,
      title: "Revenue",
      kind: "chart",
      template: "Chart",
      notes: [
        { code: "intent_not_shown", field: "highlight" },
        { code: "intent_not_shown", field: "sort" },
        { code: "intent_not_shown", field: "target" },
      ],
    };
    const dialog = open(await mount("en", [slide]));
    const notes = [...dialog.querySelectorAll("ol > li li")].map((li) => li.textContent);
    expect(notes).toEqual([
      "The emphasis asked on one part of the chart could not be shown.",
      "The chart keeps the order given: it could not be sorted as asked.",
      "An emphasis you asked for could not be shown.",
    ]);
  });

  it("says where a slide's figures could not be confirmed", async () => {
    const slide: BuiltSlide = {
      number: 2,
      part: 1,
      parts: 1,
      title: "Ventes",
      kind: "chart",
      template: "Chart",
      notes: [{ code: "illustrative_data" }, { code: "figures_unverified" }, { code: "wide_range_chart" }],
    };
    const dialog = open(await mount("fr", [slide]));
    const notes = [...dialog.querySelectorAll("ol > li li")].map((li) => li.textContent);
    expect(notes).toEqual([
      fr.capability.ppt_builder.summary.notes.illustrative_data,
      fr.capability.ppt_builder.summary.notes.figures_unverified,
      fr.capability.ppt_builder.summary.notes.wide_range_chart,
    ]);
  });

  it("has a wording for every note code the backend sends", () => {
    const codes = [
      "text_shortened",
      "content_left_out",
      "items_left_out_one",
      "items_left_out_other",
      "image_unusable_one",
      "image_unusable_other",
      "table_left_out",
      "table_text_smaller",
      "text_overflows",
      "left_empty",
      "fixed_slide",
      "list_continues",
      "list_continuation",
      "other_kind",
      "chart_type_changed",
      "chart_shows_shares",
      "layout_repeated",
      "layout_not_repeated",
      "intent_not_shown",
      "intent_not_shown_highlight",
      "intent_not_shown_sort",
      "intent_not_shown_stacked_as",
      "illustrative_data",
      "figures_unverified",
      "wide_range_chart",
    ];
    for (const locale of [en, fr]) {
      expect(Object.keys(locale.capability.ppt_builder.summary.notes).sort()).toEqual([...codes].sort());
    }
  });
});
