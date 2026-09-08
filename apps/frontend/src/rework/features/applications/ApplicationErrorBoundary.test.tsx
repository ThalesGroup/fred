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

import { act, Component, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApplicationErrorBoundary, reportCaughtReactError } from "./ApplicationErrorBoundary.tsx";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// Stands in for whatever an application's own render puts in an error: the
// assertions below fail if any of it reaches a log sink.
const PAYLOAD = "row 42 of the tenant ledger";

function Boom(): ReactNode {
  throw new Error(PAYLOAD);
}

/** Any other boundary in the app — React's raw report must survive for these. */
class PlainBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? <p>plain fallback</p> : this.props.children;
  }
}

let container: HTMLDivElement | undefined;
let root: Root | undefined;

/** The root wiring from index.tsx, so errorInfo is the one React itself builds. */
function render(node: ReactNode) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container, { onCaughtError: reportCaughtReactError });
  act(() => root?.render(node));
  return container;
}

function loggedArguments(spy: ReturnType<typeof vi.spyOn>) {
  return spy.mock.calls.flat();
}

afterEach(() => {
  if (root) act(() => root?.unmount());
  container?.remove();
  root = undefined;
  container = undefined;
  vi.restoreAllMocks();
});

describe("ApplicationErrorBoundary", () => {
  it("renders the fallback and names the application without repeating the error", () => {
    const reported = vi.spyOn(console, "error").mockImplementation(() => undefined);

    const page = render(
      <ApplicationErrorBoundary applicationId="example" fallback={<p>host fallback</p>}>
        <Boom />
      </ApplicationErrorBoundary>,
    );

    expect(page.textContent).toContain("host fallback");
    expect(reported.mock.calls).toEqual([["[applications] render failure for example"]]);
  });

  it("keeps the caught-error reporter silent for an application failure", () => {
    const reported = vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(
      <ApplicationErrorBoundary applicationId="example" fallback={<p>host fallback</p>}>
        <Boom />
      </ApplicationErrorBoundary>,
    );

    const logged = loggedArguments(reported);
    expect(logged.some((entry) => entry instanceof Error)).toBe(false);
    expect(JSON.stringify(logged)).not.toContain(PAYLOAD);
  });

  it("still reports the raw error for a boundary outside application hosting", () => {
    const reported = vi.spyOn(console, "error").mockImplementation(() => undefined);

    const page = render(
      <PlainBoundary>
        <Boom />
      </PlainBoundary>,
    );

    expect(page.textContent).toContain("plain fallback");
    const logged = loggedArguments(reported);
    const errors = logged.filter((entry): entry is Error => entry instanceof Error);
    expect(errors.map((entry) => entry.message)).toEqual([PAYLOAD]);
  });
});
