// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import type { SelectProps } from "@shared/molecules/Select/Select";
import type {
  MarketplaceEntryDetail,
  MarketplaceProposal,
  InstallationReceipt,
  ProposalSpace,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
const identity = vi.hoisted(() => ({ current: "viewer-session" as string | null }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}));
vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetToken: () => identity.current,
    GetUserId: () => "viewer",
    GetSessionIdentity: () => identity.current,
    ensureFreshToken: async () => false,
    CallLogout: vi.fn(),
  },
}));
vi.mock("../../../../common/platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));
vi.mock("@shared/molecules/Select/Select", () => ({
  default: (props: SelectProps<string>) => (
    <select
      aria-label={props.label}
      value={props.value ?? ""}
      disabled={props.disabled}
      onChange={(event) => props.onChange(event.target.value)}
    >
      <option value="" />
      {props.options.map((item) => (
        <option key={item.key} value={item.value}>
          {item.label}
        </option>
      ))}
    </select>
  ),
}));
import { enhancedControlPlaneApi as api } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { ConfirmationDialogProvider } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import MarketplaceTopPrompts from "../HomePage/MarketplaceTopPrompts/MarketplaceTopPrompts";
import { CROSS_SESSION_REFRESH_INTERVAL_MS } from "@core/hooks/crossSessionRefresh";
vi.mock("@core/hooks/useWorkingOrganization", async () => {
  const { useMarketplacesQuery } = await import("../../../../slices/controlPlane/controlPlaneApiEnhancements");
  const { sessionQueryArgs } = await import("../../../../slices/controlPlane/controlPlaneApi");
  return {
    useWorkingOrganization: () => {
      const marketplaces = useMarketplacesQuery(sessionQueryArgs({}), { refetchOnMountOrArgChange: true });
      return { organizationId: "catalogue", marketplaces, loading: marketplaces.isLoading };
    },
  };
});
import MarketplacePage from "./MarketplacePage";
import MarketplaceDetailDialog from "./MarketplaceDetailDialog";
import MarketplaceProposalDialog from "./MarketplaceProposalDialog";
import PromptsPage from "../PromptsPage/PromptsPage";
import { promptSummaryFixture } from "../PromptsPage/weaverPromptFixtures";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const NativeRequest = globalThis.Request;
const catalogue = "catalogue";
const base = `/control-plane/v1/spaces/${catalogue}/marketplace`;
const snapshot: MarketplaceEntryDetail = {
  entry_id: "entry-1",
  proposal_id: "proposal-1",
  marketplace_space_id: catalogue,
  kind: "prompt",
  publication_version: 4,
  published_at: "2026-11-08",
  display_name: "Same name",
  origin_name: "Private source",
  description: "Frozen description",
  package_hash: "hash",
  can_withdraw: false,
  package: {
    kind: "prompt",
    content: { display_name: "Same name", logical_name: "saved", tags: [], text: "FROZEN TEXT" },
  },
};
const receipt: InstallationReceipt = {
  installation_id: "receipt",
  entry_id: "entry-1",
  proposal_id: "proposal-1",
  package_hash: "hash",
  kind: "prompt",
  space_id: "destination",
  resource_id: "new-prompt",
  resource_exists: true,
  installed_at: "2026-11-08",
};
const source = {
  kind: "prompt" as const,
  source_space_id: "destination",
  source_resource_id: "source",
  expected_revision: "saved-revision",
};
const proposalFixture = (): MarketplaceProposal => ({
  ...snapshot,
  actions: { can_decide: true, can_cancel: false },
  proposing_space_id: "destination",
  submitted_by: "someone-else",
  submitted_at: "2026-11-08",
  state: "pending",
  published_proposal_id: "older",
  package: snapshot.package,
});
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
let root: Root;
let host: HTMLDivElement;
let store: ReturnType<typeof makeStore>;
let calls: Request[];
let proposal: MarketplaceProposal;
let deleted: boolean;
let override: (request: Request) => Promise<Response | undefined>;
const makeStore = () =>
  configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (defaults) => defaults().concat(api.middleware),
  });
const page = (items: unknown[]) => json({ items, next_cursor: null });

beforeEach(() => {
  sessionStorage.clear();
  identity.current = "viewer-session";
  proposal = proposalFixture();
  deleted = false;
  calls = [];
  override = async () => undefined;
  vi.stubGlobal(
    "Request",
    class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(typeof input === "string" ? new URL(input, "http://localhost") : input, init);
      }
    },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      calls.push(request.clone());
      const replacement = await override(request.clone());
      if (replacement) return replacement;
      const url = new URL(request.url);
      const path = url.pathname;
      if (path.endsWith("/me/spaces"))
        return json([{ id: "destination", kind: "personal", name: "My space", organization_id: catalogue }]);
      if (path.endsWith("/authorize/space")) return json({ allowed: true });
      if (path.endsWith("/spaces/destination/prompts"))
        return page([promptSummaryFixture({ space_id: "destination" })]);
      if (path.endsWith("/me/marketplaces")) return page([{ space_id: catalogue, name: "Organization" }]);
      if (path.endsWith("/me/marketplace-proposal-spaces"))
        return page([
          {
            id: "destination",
            name: "My space",
            kind: "personal",
            parent_id: null,
            path: ["destination"],
            personal_owner: "viewer",
            marketplace_space_ids: [catalogue],
            resource_kinds: ["prompt", "skill", "agent"],
          } satisfies ProposalSpace,
          { id: "incompatible", name: "Wrong kind", resource_kinds: ["skill"], marketplace_space_ids: [catalogue] },
        ]);
      if (path.endsWith("/prompt-categories")) return page([]);
      if (path === `${base}/entries`) return page([snapshot]);
      if (path === `${base}/entries/entry-1`) return json(snapshot);
      if (path === `${base}/proposals`) return request.method === "POST" ? json(proposal) : page([proposal]);
      if (path === `${base}/proposals/proposal-1`) return json(proposal);
      if (path.endsWith("/decision")) {
        proposal = { ...proposal, state: "approved", actions: { can_decide: false, can_cancel: false } };
        return json(proposal);
      }
      if (path.endsWith("/installations")) return json(receipt);
      if (path.endsWith("/marketplace-installations/receipt")) return json({ ...receipt, resource_exists: !deleted });
      throw new Error(`Unexpected request: ${request.method} ${path}`);
    }),
  );
  store = makeStore();
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  store.dispatch(api.util.resetApiState());
  host.remove();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});
async function mount(element: React.ReactNode, search = "") {
  await act(async () => {
    root.render(
      <Provider store={store}>
        <MemoryRouter initialEntries={[`/team/destination/prompts${search}`]}>
          <ConfirmationDialogProvider>
            <Routes>
              <Route path="/team/:teamId/prompts" element={element} />
            </Routes>
          </ConfirmationDialogProvider>
        </MemoryRouter>
      </Provider>,
    );
  });
}
const button = (label: string) =>
  Array.from(document.querySelectorAll("button"))
    .reverse()
    .find(
      (item) => item.textContent?.trim().endsWith(`rework.localMarketplace.${label}`) && !item.closest("[hidden]"),
    )!;
async function ready(label: string) {
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(button(label)).toBeDefined();
    expect(button(label).disabled).toBe(false);
  });
}
async function click(label: string) {
  await act(async () => button(label).click());
}
async function choose(label: string, value: string) {
  await act(async () => {
    const select = document.querySelector(`select[aria-label="rework.localMarketplace.${label}"]`) as HTMLSelectElement;
    select.value = value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}
const writes = (suffix: string) =>
  calls.filter((call) => call.method !== "GET" && new URL(call.url).pathname.endsWith(suffix));

it("admits an organization participant without source-library requests and keeps homonyms from every page distinct", async () => {
  override = async (request) => {
    const url = new URL(request.url);
    if (url.pathname === `${base}/entries`)
      return json(
        url.searchParams.has("after")
          ? { items: [{ ...snapshot, entry_id: "entry-2", proposal_id: "proposal-2" }], next_cursor: null }
          : { items: [snapshot], next_cursor: "entry-1" },
      );
  };
  await mount(<MarketplacePage kind="prompt" />);
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(host.querySelectorAll("article")).toHaveLength(2);
  });
  expect(host.textContent).not.toContain("entry-1");
  expect(host.textContent).not.toContain("entry-2");
  const cards = host.querySelectorAll("article");
  await act(async () => cards[1].querySelector("button")!.click());
  await vi.waitFor(() => expect(calls.some((call) => call.url.endsWith("/entries/entry-2"))).toBe(true));
  expect(calls.every((call) => !/\/prompts|\/me\/spaces|authorize/.test(new URL(call.url).pathname))).toBe(true);
  expect(calls.some((call) => new URL(call.url).searchParams.get("after") === "entry-1")).toBe(true);
});

it("examines only the frozen package and takes decision/cancellation actions from the backend", async () => {
  proposal.actions = { can_decide: false, can_cancel: true };
  await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} proposalId="proposal-1" onClose={() => {}} />);
  await ready("cancelProposal");
  expect(document.body.textContent).toContain("FROZEN TEXT");
  expect(button("approve")).toBeUndefined();
  expect(button("reject")).toBeUndefined();
  expect(
    calls.every((call) => [`${base}/proposals/proposal-1`, `${base}/proposals`].includes(new URL(call.url).pathname)),
  ).toBe(true);
});

it("reloads a conflicting publication but never approves the new version without a fresh review and click", async () => {
  let conflict = true;
  override = async (request) => {
    if (request.url.endsWith("/decision") && conflict) {
      conflict = false;
      proposal.publication_version = 5;
      return json({ code: "publication_changed", detail: "Changed" }, 409);
    }
  };
  await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} proposalId="proposal-1" onClose={() => {}} />);
  await ready("approve");
  await click("approve");
  await ready("reviewAgainAction");
  expect(writes("/decision")).toHaveLength(1);
  expect(button("approve")?.disabled).toBe(true);
  await click("reviewAgainAction");
  await ready("approve");
  expect(writes("/decision")).toHaveLength(1);
  await click("approve");
  await vi.waitFor(() => expect(writes("/decision")).toHaveLength(2));
  expect((await writes("/decision")[0].json()).expected_publication_version).toBe(4);
  expect((await writes("/decision")[1].json()).expected_publication_version).toBe(5);
});

it("submits a personal source without decision rights, blocks double clicks and retries identical content/key after network loss", async () => {
  proposal.actions = { can_decide: false, can_cancel: true };
  let loseResponse = true;
  override = async (request) => {
    if (request.method === "POST" && request.url.endsWith("/proposals") && loseResponse) {
      loseResponse = false;
      throw new TypeError("Lost response");
    }
    return undefined;
  };
  await mount(<MarketplaceProposalDialog source={source} onClose={() => {}} />);
  await ready("submit");
  await act(async () => {
    button("submit").click();
    button("submit").click();
  });
  await ready("retry");
  expect(writes("/proposals")).toHaveLength(1);
  await click("retry");
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(document.body.textContent).toContain("rework.localMarketplace.submitted");
  });
  const requests = writes("/proposals");
  expect(requests).toHaveLength(2);
  expect(requests[0].headers.get("Idempotency-Key")).toBe(requests[1].headers.get("Idempotency-Key"));
  expect(await requests[0].json()).toEqual(source);
  expect(await requests[1].json()).toEqual(source);
  await click("newOperation");
  await ready("submit");
  await click("submit");
  await vi.waitFor(() => expect(writes("/proposals")).toHaveLength(3));
  expect(writes("/proposals")[2].headers.get("Idempotency-Key")).not.toBe(requests[0].headers.get("Idempotency-Key"));
});

it("sends entry_id only after explicit replacement selection", async () => {
  await mount(<MarketplaceProposalDialog source={source} onClose={() => {}} />);
  await ready("submit");
  await choose("proposalTarget", "entry-1");
  await click("submit");
  await vi.waitFor(() => expect(writes("/proposals")).toHaveLength(1));
  expect(await writes("/proposals")[0].json()).toEqual({ ...source, entry_id: "entry-1" });
});

it.each([false, true])(
  "installs the exact proposal and uses the receipt in its destination (deleted=%s)",
  async (resourceDeleted) => {
    deleted = resourceDeleted;
    await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} entryId="entry-1" onClose={() => {}} />);
    await vi.waitFor(async () => {
      await act(async () => {});
      expect(document.querySelector('select[aria-label="rework.localMarketplace.destination"]')).not.toBeNull();
    });
    expect(document.querySelector('option[value="incompatible"]')).toBeNull();
    await choose("destination", "destination");
    await ready("install");
    await click("install");
    await vi.waitFor(async () => {
      await act(async () => {});
      expect(document.body.textContent).toContain(
        resourceDeleted ? "rework.localMarketplace.resourceDeleted" : "rework.localMarketplace.openResource",
      );
    });
    expect(await writes("/installations")[0].json()).toEqual({
      destination_space_id: "destination",
      proposal_id: "proposal-1",
      options: { kind: "prompt", logical_name: "saved", category_id: null },
    });
    const link = document.querySelector('a[href^="/team/"][href*="resource="]');
    if (resourceDeleted) expect(link).toBeNull();
    else expect(link?.getAttribute("href")).toBe("/team/destination/prompts?resource=new-prompt");
  },
);

it("hides cached packages and actions when a refreshed detail is denied", async () => {
  await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} proposalId="proposal-1" onClose={() => {}} />);
  await ready("approve");
  override = async () => json({ detail: "No access" }, 403);
  await act(async () => {
    store.dispatch(api.util.invalidateTags([{ type: "MarketplaceContent", id: catalogue }]));
  });
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(button("reviewAgainAction")).toBeDefined();
  });
  expect(document.body.textContent).not.toContain("FROZEN TEXT");
  expect(button("approve")).toBeUndefined();
});

it("withdraws only the examined version and never deletes installed copies", async () => {
  const close = vi.fn();
  override = async (request) => {
    if (request.url.endsWith("/entries/entry-1")) return json({ ...snapshot, can_withdraw: true });
    if (request.url.endsWith("/withdrawal")) return new Response(null, { status: 204 });
  };
  await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} entryId="entry-1" onClose={close} />);
  await ready("withdraw");
  await click("withdraw");
  await confirm();
  await vi.waitFor(() => expect(close).toHaveBeenCalledOnce());
  expect(await writes("/withdrawal")[0].json()).toEqual({ expected_publication_version: 4 });
  expect(calls.some((request) => request.method === "DELETE")).toBe(false);
});

it("does not present a partial catalogue when a later page fails", async () => {
  override = async (request) => {
    const url = new URL(request.url);
    if (url.pathname === `${base}/entries`)
      return url.searchParams.has("after")
        ? json({ detail: "Unavailable" }, 503)
        : json({ items: [snapshot], next_cursor: "entry-1" });
  };
  await mount(<MarketplacePage kind="prompt" />);
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(host.querySelector('[role="alert"]')).not.toBeNull();
  });
  expect(host.querySelectorAll("article")).toHaveLength(0);
  expect(host.textContent).not.toContain("Same name");
});

it("surfaces name conflicts without overwriting, silently renaming or retrying", async () => {
  override = async (request) =>
    request.url.endsWith("/installations")
      ? json({ code: "name_conflict", detail: "Local identifier already exists" }, 409)
      : undefined;
  await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} entryId="entry-1" onClose={() => {}} />);
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(document.querySelector('option[value="destination"]')).not.toBeNull();
  });
  await choose("destination", "destination");
  await ready("install");
  await click("install");
  await ready("correctRequest");
  expect(button("retry")).toBeUndefined();
  expect(document.body.textContent).toContain("rework.localMarketplace.nameConflict");
  await click("correctRequest");
  await ready("install");
  expect(
    (document.querySelector('select[aria-label="rework.localMarketplace.destination"]') as HTMLSelectElement).value,
  ).toBe("destination");
  expect(writes("/installations")).toHaveLength(1);
  expect((await writes("/installations")[0].json()).options.logical_name).toBe("saved");
  expect(document.querySelector('a[href^="/team/"][href*="resource="]')).toBeNull();
});

it.each(["skill", "agent"] as const)(
  "inspects the submitted %s files and configuration without a source read",
  async (kind) => {
    proposal.kind = kind;
    proposal.package =
      kind === "skill"
        ? {
            kind,
            content: { name: "skill", files: { "SKILL.md": "Frozen skill", "reference.txt": "Frozen reference" } },
          }
        : {
            kind,
            content: {
              display_name: "Agent",
              logical_name: "agent",
              runtime_id: "native",
              template_agent_id: "ralph",
              role: "Assist",
              usage_statement: "Use it",
              tuning_field_values: { prompt: "Frozen tuning" },
              capabilities: {
                ppt_builder: { schema_version: "1", config: { mode: "frozen" }, files: { "template.pptx": "YWJj" } },
              },
              model_options: {},
            },
          };
    await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} proposalId="proposal-1" onClose={() => {}} />);
    await ready("approve");
    if (kind === "skill") {
      expect(document.body.textContent).toContain("Frozen skill");
      expect(document.body.textContent).toContain("reference.txt");
    } else {
      expect(document.body.textContent).toContain("Frozen tuning");
      expect(document.body.textContent).toContain('"mode": "frozen"');
      expect(document.querySelector('a[download="template.pptx"]')?.getAttribute("href")).toBe(
        "data:application/octet-stream;base64,YWJj",
      );
    }
    expect(
      calls.every((request) =>
        [`${base}/proposals/proposal-1`, `${base}/proposals`].includes(new URL(request.url).pathname),
      ),
    ).toBe(true);
  },
);

// A fresh React tree and Redux store model reload; browser session storage survives.
async function reload(element: React.ReactNode, search = "") {
  await act(async () => root.unmount());
  store.dispatch(api.util.resetApiState());
  store = makeStore();
  root = createRoot(host);
  await mount(element, search);
}
async function openPromptProposal() {
  await settledDiscovery();
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(document.querySelector('[aria-label^="rework.weaverPrompts.actions"]')).not.toBeNull();
  });
  await act(async () =>
    (document.querySelector('[aria-label^="rework.weaverPrompts.actions"]') as HTMLElement).click(),
  );
  await act(async () =>
    (
      Array.from(document.querySelectorAll('[role="option"]')).find((item) =>
        item.textContent?.includes("localMarketplace.propose"),
      ) as HTMLElement
    ).click(),
  );
}
const settledDiscovery = () =>
  vi.waitFor(async () => {
    await act(async () => {});
    expect(api.endpoints.marketplaceProposalSpaces.select({})(store.getState()).status).toBe("fulfilled");
  });
const discoveryCalls = () =>
  calls.filter((request) => new URL(request.url).pathname.endsWith("/me/marketplace-proposal-spaces"));

it("keeps the real prompt proposal dialog stable through mounting, focus and discovery invalidation", async () => {
  override = async (request) => {
    if (new URL(request.url).pathname.endsWith("/me/marketplace-proposal-spaces")) {
      if (discoveryCalls().length > 10) return json({ detail: "Refetch loop" }, 503);
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
  };
  await mount(<PromptsPage />);
  await openPromptProposal();
  await ready("submit");
  await settledDiscovery();
  const dialog = document.querySelector('[role="dialog"]');
  expect(dialog).not.toBeNull();
  button("submit").focus();
  const focused = document.activeElement;
  let release: (() => void) | undefined;
  override = async (request) => {
    if (new URL(request.url).pathname.endsWith("/me/marketplace-proposal-spaces"))
      await new Promise<void>((resolve) => {
        release = resolve;
      });
    return undefined;
  };
  await act(async () => window.dispatchEvent(new Event("focus")));
  await vi.waitFor(() => expect(release).toBeDefined());
  expect(document.querySelector('[role="dialog"]')).toBe(dialog);
  expect(document.activeElement).toBe(focused);
  await act(async () => release!());
  await settledDiscovery();
  await ready("submit");
  release = undefined;
  await act(async () => {
    store.dispatch(api.util.invalidateTags(["Marketplaces"]));
  });
  await vi.waitFor(() => expect(release).toBeDefined());
  expect(document.querySelector('[role="dialog"]')).toBe(dialog);
  expect(document.activeElement).toBe(focused);
  await act(async () => release!());
  await settledDiscovery();
  await ready("submit");
  expect(discoveryCalls().length).toBeLessThanOrEqual(4);
});

it.each(["empty", "forbidden"])(
  "blocks proposal actions after confirmed discovery revocation (%s)",
  async (response) => {
    await mount(<PromptsPage />);
    await openPromptProposal();
    await ready("submit");
    await settledDiscovery();
    override = async (request) =>
      new URL(request.url).pathname.endsWith("/me/marketplace-proposal-spaces")
        ? response === "empty"
          ? page([])
          : json({ detail: "Revoked" }, 403)
        : undefined;
    await act(async () => {
      store.dispatch(api.util.invalidateTags(["Marketplaces"]));
    });
    await vi.waitFor(async () => {
      await act(async () => {});
      expect(button("submit")).toBeUndefined();
    });
    let release: (() => void) | undefined;
    const denied = override;
    override = async (request) => {
      if (new URL(request.url).pathname.endsWith("/me/marketplace-proposal-spaces"))
        await new Promise<void>((resolve) => {
          release = resolve;
        });
      return denied(request);
    };
    await act(async () => window.dispatchEvent(new Event("focus")));
    await vi.waitFor(() => expect(release).toBeDefined());
    expect(button("submit")?.disabled ?? true).toBe(true);
    await act(async () => release!());
    await vi.waitFor(async () => {
      await act(async () => {});
      expect(button("submit")).toBeUndefined();
    });
    expect(writes("/proposals")).toHaveLength(0);
  },
);

it.each([false, true])(
  "recovers an accepted prompt proposal after closure/reopening (reload=%s) with the original request/key",
  async (reload) => {
    let acceptedKey: string | null | undefined;
    let acceptedBody: unknown;
    let revised = false;
    override = async (request) => {
      if (revised && new URL(request.url).pathname.endsWith("/spaces/destination/prompts"))
        return page([promptSummaryFixture({ space_id: "destination", updated_at: "2026-11-09T12:00:00Z" })]);
      if (request.method === "POST" && new URL(request.url).pathname.endsWith("/proposals")) {
        const key = request.headers.get("Idempotency-Key");
        if (!acceptedKey) {
          acceptedKey = key;
          acceptedBody = await request.json();
          throw new TypeError("Accepted, response lost");
        }
        expect(key).toBe(acceptedKey);
        expect(await request.json()).toEqual(acceptedBody);
        return json(proposal);
      }
    };
    await mount(<PromptsPage />);
    await openPromptProposal();
    await ready("submit");
    await click("submit");
    await ready("retry");
    await click("close");
    if (reload) {
      await act(async () => root.unmount());
      store.dispatch(api.util.resetApiState());
      store = makeStore();
      root = createRoot(host);
      revised = true;
      await mount(<PromptsPage />);
    }
    await openPromptProposal();
    await ready("retry");
    expect(button("newOperation")).toBeUndefined();
    expect(writes("/proposals")).toHaveLength(1);
    await click("retry");
    await vi.waitFor(async () => {
      await act(async () => {});
      expect(document.body.textContent).toContain("rework.localMarketplace.submitted");
    });
    expect(writes("/proposals")).toHaveLength(2);
    const persisted = Array.from({ length: sessionStorage.length }, (_, index) =>
      JSON.parse(sessionStorage.getItem(sessionStorage.key(index)!)!),
    );
    expect(persisted).toHaveLength(0);
  },
);

it("never reuses another identity's attempt, including an identity change in an open dialog", async () => {
  override = async (request) => {
    if (request.method === "POST" && new URL(request.url).pathname.endsWith("/proposals"))
      throw new TypeError("Lost response");
    return undefined;
  };
  await mount(<PromptsPage />);
  await openPromptProposal();
  await ready("submit");
  await click("submit");
  await ready("retry");
  const first = writes("/proposals")[0].headers.get("Idempotency-Key");
  identity.current = "another-issuer/viewer";
  // A stale click must not send the first identity's request with the new bearer.
  await click("retry");
  expect(writes("/proposals")).toHaveLength(1);
  await click("close");
  await reload(<PromptsPage />);
  await openPromptProposal();
  await ready("submit");
  await click("submit");
  await ready("retry");
  expect(writes("/proposals")[1].headers.get("Idempotency-Key")).not.toBe(first);
  await click("close");
  identity.current = "viewer-session";
  await reload(<PromptsPage />);
  await openPromptProposal();
  await ready("retry");
  await click("retry");
  expect(writes("/proposals")[2].headers.get("Idempotency-Key")).toBe(first);
});

it.each([false, true])(
  "recovers an installation from the server after unmount (reload=%s), without storing its package or receipt",
  async (reload) => {
    let accepted = false;
    override = async (request) => {
      if (request.method === "POST" && new URL(request.url).pathname.endsWith("/installations") && !accepted) {
        accepted = true;
        throw new TypeError("Installed, response lost");
      }
      return undefined;
    };
    const detail = <MarketplaceDetailDialog marketplaceSpaceId={catalogue} entryId="entry-1" onClose={() => {}} />;
    await mount(detail);
    await vi.waitFor(async () => {
      await act(async () => {});
      expect(document.querySelector('select[aria-label="rework.localMarketplace.destination"]')).not.toBeNull();
    });
    await choose("destination", "destination");
    await ready("install");
    await click("install");
    await ready("retry");
    const first = writes("/installations")[0];
    if (reload) {
      await act(async () => root.unmount());
      store.dispatch(api.util.resetApiState());
      store = makeStore();
      root = createRoot(host);
    } else await mount(<></>);
    deleted = true;
    await mount(detail);
    await ready("retry");
    expect(writes("/installations")).toHaveLength(1);
    expect(button("newOperation")).toBeUndefined();
    await click("retry");
    await vi.waitFor(async () => {
      await act(async () => {});
      expect(document.body.textContent).toContain("rework.localMarketplace.resourceDeleted");
    });
    const retried = writes("/installations")[1];
    expect(retried.headers.get("Idempotency-Key")).toBe(first.headers.get("Idempotency-Key"));
    expect(await retried.clone().json()).toEqual(await first.clone().json());
    const persisted = JSON.parse(sessionStorage.getItem(sessionStorage.key(0)!)!);
    expect(persisted).toBeNull();
  },
);

it("lets the backend deny an unresolved proposal after source rights are revoked", async () => {
  override = async (request) => {
    if (request.method === "POST" && new URL(request.url).pathname.endsWith("/proposals"))
      throw new TypeError("Lost response");
    return undefined;
  };
  await mount(<MarketplaceProposalDialog source={source} onClose={() => {}} />);
  await ready("submit");
  await click("submit");
  await ready("retry");
  override = async (request) => {
    const path = new URL(request.url).pathname;
    if (path.endsWith("/me/marketplace-proposal-spaces")) return page([]);
    if (request.method === "POST" && path.endsWith("/proposals")) return json({ detail: "Replay denied" }, 403);
  };
  await act(async () => {
    store.dispatch(api.util.invalidateTags(["Marketplaces"]));
  });
  await ready("retry");
  await click("retry");
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(document.body.textContent).toContain("rework.localMarketplace.forbidden");
  });
  expect(document.querySelector('a[href*="proposal="]')).toBeNull();
  expect(writes("/proposals")).toHaveLength(2);
});

it("does not send an operation whose recovery information cannot be persisted", async () => {
  await mount(<PromptsPage />);
  await openPromptProposal();
  await ready("submit");
  const originalStorage = sessionStorage;
  vi.stubGlobal("sessionStorage", {
    getItem: (key: string) => originalStorage.getItem(key),
    setItem: () => {
      throw new DOMException("Full", "QuotaExceededError");
    },
  });
  await click("submit");
  expect(document.body.textContent).toContain("rework.localMarketplace.attemptStorageUnavailable");
  expect(writes("/proposals")).toHaveLength(0);
});

it.each(["allowed", "replay-denied", "receipt-denied"])(
  "recovers the same installation after acceptance, lost response, withdrawal and reload without duplication (%s)",
  async (access) => {
    let withdrawn = false;
    const installations = new Map<string, { body: unknown; receipt: InstallationReceipt }>();
    override = async (request) => {
      const path = new URL(request.url).pathname;
      if (withdrawn && path === `${base}/entries`) return page([]);
      if (withdrawn && path === `${base}/entries/entry-1`) return json({ detail: "Withdrawn" }, 404);
      if (request.method === "POST" && path.endsWith("/installations")) {
        const key = request.headers.get("Idempotency-Key")!;
        const body = await request.json();
        const previous = installations.get(key);
        if (withdrawn && access === "replay-denied") return json({ detail: "Installation replay denied" }, 403);
        if (previous) {
          expect(body).toEqual(previous.body);
          return json(previous.receipt);
        }
        if (withdrawn) return json({ code: "publication_changed", detail: "Withdrawn" }, 409);
        installations.set(key, { body, receipt });
        throw new TypeError("Installation accepted, response lost");
      }
      if (path.endsWith("/marketplace-installations/receipt") && access === "receipt-denied")
        return json({ detail: "Receipt access denied" }, 403);
      return undefined;
    };
    await mount(<MarketplacePage kind="prompt" />);
    await ready("inspect");
    await click("inspect");
    await vi.waitFor(async () => {
      await act(async () => {});
      expect(document.querySelector('option[value="destination"]')).not.toBeNull();
    });
    await choose("destination", "destination");
    await ready("install");
    await click("install");
    await ready("retry");
    const original = writes("/installations")[0];
    expect(installations.size).toBe(1);
    withdrawn = true;
    const reloadStart = calls.length;
    await reload(<MarketplacePage kind="prompt" />, `?catalogue=${catalogue}&entry=entry-1`);
    await ready("retry");
    await vi.waitFor(async () => {
      await act(async () => {});
      expect(document.body.textContent).toContain("Withdrawn");
    });
    expect(document.body.textContent).not.toContain("FROZEN TEXT");
    expect(button("install")).toBeUndefined();
    expect(button("newOperation")).toBeUndefined();
    expect(writes("/installations")).toHaveLength(1);
    await click("retry");
    await vi.waitFor(async () => {
      await act(async () => {});
      expect(document.body.textContent).toContain(
        access === "allowed"
          ? "rework.localMarketplace.openResource"
          : access === "replay-denied"
            ? "rework.localMarketplace.forbidden"
            : "rework.localMarketplace.forbidden",
      );
    });
    expect(writes("/installations")).toHaveLength(2);
    const retried = writes("/installations")[1];
    expect(retried.headers.get("Idempotency-Key")).toBe(original.headers.get("Idempotency-Key"));
    expect(await retried.json()).toEqual(await original.json());
    expect(installations.size).toBe(1);
    expect(button("install")).toBeUndefined();
    expect(button("newOperation")).toBeUndefined();
    const link = document.querySelector('a[href^="/team/"][href*="resource="]');
    if (access === "allowed") expect(link?.getAttribute("href")).toBe("/team/destination/prompts?resource=new-prompt");
    else expect(link).toBeNull();
    const recoveryCalls = calls.slice(reloadStart).map((request) => new URL(request.url).pathname);
    expect(recoveryCalls.some((path) => path.endsWith("/marketplace-installations/receipt"))).toBe(
      access !== "replay-denied",
    );
    expect(
      recoveryCalls.some(
        (path) => path.endsWith("/me/marketplace-proposal-spaces") || path.endsWith("/prompt-categories"),
      ),
    ).toBe(false);
    // Without a saved operation, an unavailable publication offers no installation.
    sessionStorage.clear();
    await reload(<MarketplacePage kind="prompt" />, `?catalogue=${catalogue}&entry=entry-1`);
    await vi.waitFor(async () => {
      await act(async () => {});
      expect(document.body.textContent).toContain("Withdrawn");
    });
    expect(button("install")).toBeUndefined();
    expect(button("retry")).toBeUndefined();
    expect(writes("/installations")).toHaveLength(2);
  },
);

it("regression: identity switch must not show the prior account's proposal or send its decision", async () => {
  await mount(<MarketplacePage kind="prompt" />, `?catalogue=${catalogue}&proposal=proposal-1`);
  await ready("approve");
  const originalDetails = calls.filter((request) =>
    new URL(request.url).pathname.endsWith("/proposals/proposal-1"),
  ).length;
  identity.current = "other-issuer/other-user";
  override = async (request) => {
    if (
      new URL(request.url).pathname.endsWith("/proposals/proposal-1") ||
      new URL(request.url).pathname.endsWith("/decision")
    )
      return json({ detail: "Private proposal" }, 403);
    return undefined;
  };
  // Reflect the new identity without destroying the existing React tree / Redux cache.
  await mount(<MarketplacePage kind="prompt" />);
  await act(async () => {});
  const stillOffered = button("approve");
  if (stillOffered) await click("approve");
  const sent = writes("/decision");
  expect(sent).toHaveLength(0);
  expect(document.body.textContent).not.toContain("FROZEN TEXT");
  expect(
    calls.filter((request) => new URL(request.url).pathname.endsWith("/proposals/proposal-1")).length,
  ).toBeGreaterThan(originalDetails);
});

it("regression: confirmed proposal revocation on focus must remove the open detail's actions and package", async () => {
  await mount(<MarketplacePage kind="prompt" />, `?catalogue=${catalogue}&proposal=proposal-1`);
  await ready("approve");
  override = async (request) => {
    const path = new URL(request.url).pathname;
    if (path === `${base}/proposals`) return page([]);
    if (path === `${base}/proposals/proposal-1`) return json({ detail: "Role revoked" }, 403);
    return undefined;
  };
  await act(async () => window.dispatchEvent(new Event("focus")));
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(document.body.textContent).toContain("rework.localMarketplace.noProposals");
  });
  expect(button("approve")).toBeUndefined();
  expect(document.body.textContent).not.toContain("FROZEN TEXT");
});

it("regression: source deletion must not block recovery of a proposal still readable by a catalogue editor", async () => {
  let accepted: { key: string | null; body: unknown } | undefined;
  let sourceGone = false;
  override = async (request) => {
    const path = new URL(request.url).pathname;
    if (path.endsWith("/me/marketplace-proposal-spaces") && sourceGone) return page([]);
    if (request.method === "POST" && path.endsWith("/proposals")) {
      if (!accepted) {
        accepted = { key: request.headers.get("Idempotency-Key"), body: await request.json() };
        throw new TypeError("Accepted, response lost");
      }
      expect(request.headers.get("Idempotency-Key")).toBe(accepted.key);
      expect(await request.json()).toEqual(accepted.body);
      return json(proposal);
    }
    return undefined;
  };
  await mount(<MarketplaceProposalDialog source={source} onClose={() => {}} />);
  await ready("submit");
  await click("submit");
  await ready("retry");
  sourceGone = true;
  await reload(<MarketplaceProposalDialog source={source} onClose={() => {}} />);
  await ready("retry");
  await click("retry");
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(document.body.textContent).toContain("rework.localMarketplace.submitted");
  });
  expect(writes("/proposals")).toHaveLength(2);
});

it("regression: a publication withdrawn in the refreshed list must not offer a fresh installation in its open dialog", async () => {
  await mount(<MarketplacePage kind="prompt" />);
  await ready("inspect");
  await click("inspect");
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(document.querySelector('option[value="destination"]')).not.toBeNull();
  });
  await choose("destination", "destination");
  await ready("install");
  override = async (request) => {
    const path = new URL(request.url).pathname;
    if (path === `${base}/entries`) return page([]);
    if (path === `${base}/entries/entry-1`) return json({ detail: "Withdrawn" }, 404);
    if (path.endsWith("/installations")) return json({ code: "publication_changed" }, 409);
    return undefined;
  };
  await act(async () => window.dispatchEvent(new Event("focus")));
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(document.body.textContent).toContain("rework.localMarketplace.noPublications");
  });
  expect(button("install")).toBeUndefined();
});

async function confirm() {
  await act(async () => {
    const confirmButton = Array.from(document.querySelectorAll("button")).find(
      (item) => item.textContent?.trim() === "confirmationDialog.defaultConfirmButtonLabel",
    );
    expect(confirmButton).toBeDefined();
    confirmButton!.click();
  });
}

function deferredResponse() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

it.each(["approve", "reject", "cancelProposal"])(
  "blocks a retained %s handler before React observes the new identity",
  async (action) => {
    proposal.actions = { can_decide: true, can_cancel: true };
    await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} proposalId="proposal-1" onClose={() => {}} />);
    await ready(action);
    identity.current = "other-session";
    await click(action);
    expect(calls.filter((request) => request.method !== "GET")).toHaveLength(0);
  },
);

it.each([false, true])("discards an old withdrawal confirmation on identity change (rerender=%s)", async (rerender) => {
  override = async (request) =>
    request.url.endsWith("/entries/entry-1") ? json({ ...snapshot, can_withdraw: true }) : undefined;
  const detail = () => <MarketplaceDetailDialog marketplaceSpaceId={catalogue} entryId="entry-1" onClose={() => {}} />;
  await mount(detail());
  await ready("withdraw");
  await click("withdraw");
  expect(document.querySelector('[role="alertdialog"]')).not.toBeNull();
  identity.current = "other-session";
  if (rerender) {
    await mount(detail());
    expect(document.querySelector('[role="alertdialog"]')).toBeNull();
    await ready("withdraw");
  } else await confirm();
  expect(writes("/withdrawal")).toHaveLength(0);
});

it("waits for B's own detail, resets the review reason and ignores a late A response", async () => {
  const lateA = deferredResponse();
  const freshB = deferredResponse();
  const detail = () => (
    <MarketplaceDetailDialog marketplaceSpaceId={catalogue} proposalId="proposal-1" onClose={() => {}} />
  );
  await mount(detail());
  await ready("approve");
  await act(async () => {
    const textarea = document.querySelector("textarea")!;
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
    setter.call(textarea, "Private A reason");
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  });
  override = async (request) => {
    if (request.url.endsWith("/proposals/proposal-1"))
      return request.headers.get("Authorization") === "Bearer viewer-session" ? lateA.promise : freshB.promise;
  };
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
  });
  await vi.waitFor(() => expect(calls.filter((r) => r.url.endsWith("/proposals/proposal-1"))).toHaveLength(2));
  identity.current = "B";
  await mount(detail());
  expect(document.body.textContent).not.toContain("FROZEN TEXT");
  expect(button("approve")).toBeUndefined();
  await vi.waitFor(() => expect(calls.filter((r) => r.url.endsWith("/proposals/proposal-1"))).toHaveLength(3));
  await act(async () =>
    freshB.resolve(
      json({ ...proposal, package: { kind: "prompt", content: { ...snapshot.package.content, text: "B TEXT" } } }),
    ),
  );

  await ready("approve");
  expect(document.querySelector("textarea")!.value).toBe("");
  await act(async () => lateA.resolve(json(proposal)));
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(document.body.textContent).toContain("B TEXT");
    expect(document.body.textContent).not.toContain("FROZEN TEXT");
  });
  expect(writes("/decision")).toHaveLength(0);
});

it.each(["focus", "explicit", "periodic"])(
  "revalidates an open detail via %s without remounting its form or sending decisions",
  async (trigger) => {
    if (trigger === "periodic") vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    await mount(<MarketplacePage kind="prompt" />);
    await ready("inspect");
    await click("inspect");
    await vi.waitFor(() => expect(document.querySelector('option[value="destination"]')).not.toBeNull());
    await choose("destination", "destination");
    await ready("install");
    const form = document.querySelector('select[aria-label="rework.localMarketplace.destination"]');
    const readsBefore = calls.filter((r) => r.url.endsWith("/entries/entry-1")).length;
    const pending = deferredResponse();
    override = async (request) => (request.url.endsWith("/entries/entry-1") ? pending.promise : undefined);
    if (trigger === "periodic") {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(CROSS_SESSION_REFRESH_INTERVAL_MS + 1);
      });
      vi.useRealTimers();
    } else if (trigger === "explicit") await click("refresh");
    else
      await act(async () => {
        window.dispatchEvent(new Event("focus"));
      });
    await vi.waitFor(async () => {
      await act(async () => {});
      expect(button("install").disabled).toBe(true);
    });
    expect(document.querySelector('select[aria-label="rework.localMarketplace.destination"]')).toBe(form);
    expect((form as HTMLSelectElement).value).toBe("destination");
    await act(async () => pending.resolve(json(snapshot)));
    await ready("install");
    expect(document.querySelector('select[aria-label="rework.localMarketplace.destination"]')).toBe(form);
    expect(calls.filter((r) => r.url.endsWith("/entries/entry-1"))).toHaveLength(readsBefore + 1);
    expect(writes("/installations")).toHaveLength(0);
  },
);

it("revalidates the detail opened from Home after withdrawal", async () => {
  await mount(<MarketplaceTopPrompts period={7} />);
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(host.querySelector('[role="button"]')).not.toBeNull();
  });
  await act(async () => (host.querySelector('[role="button"]') as HTMLElement).click());
  await vi.waitFor(() => expect(document.body.textContent).toContain("FROZEN TEXT"));
  override = async (request) => {
    const path = new URL(request.url).pathname;
    if (path === `${base}/entries`) return page([]);
    if (path === `${base}/entries/entry-1`) return json({ detail: "Withdrawn at Home" }, 404);
  };
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
  });
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(document.body.textContent).toContain("Withdrawn at Home");
  });
  expect(document.body.textContent).not.toContain("FROZEN TEXT");
  expect(button("install")).toBeUndefined();
});

it.each([false, true])(
  "recovers from the catalogue after source deletion using exactly the saved request (denied=%s)",
  async (denied) => {
    let gone = false;
    let accepted: { key: string | null; body: unknown } | undefined;
    override = async (request) => {
      const path = new URL(request.url).pathname;
      if (gone && path.endsWith("/me/marketplace-proposal-spaces")) return page([]);
      if (gone && path.endsWith("/me/spaces")) return json([]);
      if (request.method === "POST" && path.endsWith("/proposals")) {
        if (!accepted) {
          accepted = { key: request.headers.get("Idempotency-Key"), body: await request.json() };
          throw new TypeError("Accepted, response lost");
        }
        expect(request.headers.get("Idempotency-Key")).toBe(accepted.key);
        expect(await request.json()).toEqual(accepted.body);
        return denied ? json({ detail: "Catalogue replay revoked" }, 403) : json(proposal);
      }
    };
    await mount(<PromptsPage />);
    await openPromptProposal();
    await ready("submit");
    await choose("proposalTarget", "entry-1");
    await click("submit");
    await ready("retry");
    const savedBefore = sessionStorage.getItem(sessionStorage.key(0)!);
    gone = true;
    await reload(<MarketplacePage kind="prompt" />);
    await ready("resumeProposal");
    expect(button("submit")).toBeUndefined();
    await click("resumeProposal");
    await ready("retry");
    expect(writes("/proposals")).toHaveLength(1);
    expect(button("newOperation")).toBeUndefined();
    await click("retry");
    await vi.waitFor(async () => {
      await act(async () => {});
      expect(document.body.textContent).toContain(
        denied ? "rework.localMarketplace.forbidden" : "rework.localMarketplace.submitted",
      );
    });
    expect(writes("/proposals")).toHaveLength(2);
    expect(sessionStorage.getItem(sessionStorage.key(0)!)).toBe(denied ? savedBefore : null);
    expect(button("newOperation")).toBeUndefined();
    expect(!!document.querySelector('a[href*="proposal="]')).toBe(!denied);
    expect(calls.some((request) => gone && new URL(request.url).pathname.includes("source/"))).toBe(false);
  },
);

it.each([200, 409])("ignores A's late decision completion in B's fresh review (status=%s)", async (status) => {
  const completion = deferredResponse();
  override = async (request) => (request.url.endsWith("/decision") ? completion.promise : undefined);
  const detail = () => (
    <MarketplaceDetailDialog marketplaceSpaceId={catalogue} proposalId="proposal-1" onClose={() => {}} />
  );
  await mount(detail());
  await ready("approve");
  await click("approve");
  await vi.waitFor(() => expect(writes("/decision")).toHaveLength(1));
  identity.current = "B";
  await mount(detail());
  await ready("approve");
  await act(async () =>
    completion.resolve(json(status === 200 ? proposal : { code: "publication_changed", detail: "A conflict" }, status)),
  );
  await ready("approve");
  expect(document.body.textContent).not.toContain("A conflict");
  expect(button("reviewAgainAction")).toBeUndefined();
  expect(writes("/decision")).toHaveLength(1);
});

it("blocks an old confirmation as soon as verification starts and after the version changes", async () => {
  const pending = deferredResponse();
  override = async (request) =>
    request.url.endsWith("/entries/entry-1") ? json({ ...snapshot, can_withdraw: true }) : undefined;
  await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} entryId="entry-1" onClose={() => {}} />);
  await ready("withdraw");
  await click("withdraw");
  override = async (request) => (request.url.endsWith("/entries/entry-1") ? pending.promise : undefined);
  await act(async () => {
    store.dispatch(api.util.invalidateTags([{ type: "MarketplaceContent", id: catalogue }]));
    const confirmButton = Array.from(document.querySelectorAll("button")).find(
      (item) => item.textContent?.trim() === "confirmationDialog.defaultConfirmButtonLabel",
    )!;
    confirmButton.click();
  });
  expect(writes("/withdrawal")).toHaveLength(0);
  await act(async () => pending.resolve(json({ ...snapshot, can_withdraw: true, publication_version: 5 })));
  await ready("withdraw");
  await click("withdraw");
  override = async (request) =>
    request.url.endsWith("/entries/entry-1")
      ? json({ ...snapshot, can_withdraw: true, publication_version: 6 })
      : undefined;
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
  });
  await ready("withdraw");
  await confirm();
  expect(writes("/withdrawal")).toHaveLength(0);
});

it("keeps an in-flight installation across detail revalidation and withdrawal", async () => {
  const completion = deferredResponse();
  let withdrawn = false;
  override = async (request) => {
    const path = new URL(request.url).pathname;
    if (path.endsWith("/installations")) return completion.promise;
    if (withdrawn && path === `${base}/entries/entry-1`) return json({ detail: "Withdrawn" }, 404);
  };
  await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} entryId="entry-1" onClose={() => {}} />);
  await vi.waitFor(() => expect(document.querySelector('option[value="destination"]')).not.toBeNull());
  await choose("destination", "destination");
  await ready("install");
  await click("install");
  await vi.waitFor(() => expect(writes("/installations")).toHaveLength(1));
  withdrawn = true;
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
  });
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(document.body.textContent).toContain("Withdrawn");
  });
  expect(button("retry").disabled).toBe(true);
  await act(async () => completion.resolve(json(receipt)));
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(document.body.textContent).toContain("rework.localMarketplace.openResource");
  });
  expect(document.body.textContent).not.toContain("FROZEN TEXT");
  expect(writes("/installations")).toHaveLength(1);
});

it("does not resurrect a refused package while the next verification is pending", async () => {
  await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} proposalId="proposal-1" onClose={() => {}} />);
  await ready("approve");
  override = async () => json({ detail: "Revoked" }, 403);
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
  });
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(document.body.textContent).toContain("rework.localMarketplace.forbidden");
  });
  expect(document.body.textContent).not.toContain("FROZEN TEXT");
  const pending = deferredResponse();
  override = async () => pending.promise;
  await click("reviewAgainAction");
  expect(document.body.textContent).not.toContain("FROZEN TEXT");
  expect(button("approve")).toBeUndefined();
  await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} proposalId="proposal-1" onClose={() => {}} />);
  expect(document.body.textContent).not.toContain("FROZEN TEXT");
  await act(async () => pending.resolve(json(proposal)));
  await ready("approve");
  expect(writes("/decision")).toHaveLength(0);
});

it.each([false, true])("blocks an old installation command after identity change (retry=%s)", async (retry) => {
  override = async (request) => {
    if (request.url.endsWith("/installations")) throw new TypeError("Accepted, response lost");
    return undefined;
  };
  await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} entryId="entry-1" onClose={() => {}} />);
  await vi.waitFor(() => expect(document.querySelector('option[value="destination"]')).not.toBeNull());
  await choose("destination", "destination");
  await ready("install");
  if (retry) {
    await click("install");
    await ready("retry");
  }
  identity.current = "B";
  await click(retry ? "retry" : "install");
  expect(writes("/installations")).toHaveLength(retry ? 1 : 0);
});

it.each([false, true])(
  "does not revive a successful installation on reopening or reload (new publication=%s)",
  async (updated) => {
    const detail = <MarketplaceDetailDialog marketplaceSpaceId={catalogue} entryId="entry-1" onClose={() => {}} />;
    await mount(detail);
    await vi.waitFor(() => expect(document.querySelector('option[value="destination"]')).not.toBeNull());
    await choose("destination", "destination");
    await ready("install");
    await click("install");
    await vi.waitFor(() => expect(document.body.textContent).toContain("rework.localMarketplace.openResource"));
    expect(sessionStorage.length).toBe(0);
    if (updated)
      override = async (request) =>
        request.url.endsWith("/entries/entry-1")
          ? json({
              ...snapshot,
              proposal_id: "proposal-2",
              publication_version: 5,
              display_name: "Updated publication",
            })
          : undefined;
    await reload(detail);
    await vi.waitFor(() => expect(document.querySelector('option[value="destination"]')).not.toBeNull());
    expect(button("retry")).toBeUndefined();
    expect(document.body.textContent).not.toContain("rework.localMarketplace.resumeAttempt");
    expect(writes("/installations")).toHaveLength(1);
    await choose("destination", "destination");
    await ready("install");
    await click("install");
    await vi.waitFor(() => expect(writes("/installations")).toHaveLength(2));
    expect((await writes("/installations")[1].json()).proposal_id).toBe(updated ? "proposal-2" : "proposal-1");
    expect(writes("/installations")[1].headers.get("Idempotency-Key")).not.toBe(
      writes("/installations")[0].headers.get("Idempotency-Key"),
    );
  },
);

it("removes completed proposals from recovery after reload", async () => {
  await mount(<MarketplaceProposalDialog source={source} sourceName="Research summary" onClose={() => {}} />);
  await ready("submit");
  await click("submit");
  await vi.waitFor(() => expect(document.body.textContent).toContain("rework.localMarketplace.submitted"));
  expect(sessionStorage.length).toBe(0);
  await reload(<MarketplacePage kind="prompt" />);
  await ready("inspect");
  expect(button("resumeProposal")).toBeUndefined();
  expect(writes("/proposals")).toHaveLength(1);
});

it("keeps the destination and permits a different identifier after a definitive conflict", async () => {
  override = async (request) =>
    request.url.endsWith("/installations") && (await request.json()).options.logical_name === "saved"
      ? json({ code: "conflict", detail: "conflicting name or resource reference" }, 409)
      : undefined;
  await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} entryId="entry-1" onClose={() => {}} />);
  await vi.waitFor(() => expect(document.querySelector('option[value="destination"]')).not.toBeNull());
  await choose("destination", "destination");
  await ready("install");
  await click("install");
  await ready("correctRequest");
  expect(sessionStorage.length).toBe(0);
  expect(button("retry")).toBeUndefined();
  await click("correctRequest");
  await act(async () => {
    const input = document.querySelector('input[value="saved"]')!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "saved-atlas");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await ready("install");
  await click("install");
  await vi.waitFor(() => expect(document.body.textContent).toContain("rework.localMarketplace.openResource"));
  const requests = writes("/installations");
  expect(requests).toHaveLength(2);
  expect(requests[1].headers.get("Idempotency-Key")).not.toBe(requests[0].headers.get("Idempotency-Key"));
  expect((await requests[1].json()).options.logical_name).toBe("saved-atlas");
  expect(calls.some((request) => ["PUT", "DELETE", "PATCH"].includes(request.method))).toBe(false);
});

it.each([false, true])(
  "refreshes the catalogue after approval despite another request in flight (old catalogue read=%s)",
  async (oldRead) => {
    const unrelated = deferredResponse();
    const stale = deferredResponse();
    let updated = false;
    let delayOldRead = false;
    override = async (request) => {
      if (request.url.endsWith("/spaces/slow/skills")) return unrelated.promise;
      if (request.url.endsWith("/decision")) updated = true;
      if (new URL(request.url).pathname === `${base}/entries`) {
        if (delayOldRead) {
          delayOldRead = false;
          return stale.promise;
        }
        return page([{ ...snapshot, display_name: updated ? "New current publication" : "Old publication" }]);
      }
    };
    const listing = store.dispatch(
      api.endpoints.marketplaceEntries.initiate({ marketplaceSpaceId: catalogue, kind: "prompt" }),
    );
    await listing;
    await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} proposalId="proposal-1" onClose={() => {}} />);
    await ready("approve");
    const slow = store.dispatch(api.endpoints.listSkills.initiate({ spaceId: "slow" }));
    if (oldRead) {
      delayOldRead = true;
      void store.dispatch(
        api.endpoints.marketplaceEntries.initiate(
          { marketplaceSpaceId: catalogue, kind: "prompt" },
          { forceRefetch: true },
        ),
      );
      await vi.waitFor(() => expect(delayOldRead).toBe(false));
    }
    await click("approve");
    await vi.waitFor(() => expect(writes("/decision")).toHaveLength(1));
    if (oldRead) await act(async () => stale.resolve(page([{ ...snapshot, display_name: "Old publication" }])));
    await vi.waitFor(async () => {
      await act(async () => {});
      expect(
        api.endpoints.marketplaceEntries.select({ marketplaceSpaceId: catalogue, kind: "prompt" })(store.getState())
          .data?.items[0].display_name,
      ).toBe("New current publication");
    });
    await act(async () => unrelated.resolve(json([])));
    await slow;
    slow.unsubscribe();
    listing.unsubscribe();
  },
);

it.each(["reject", "cancelProposal"])("refreshes the server decision after %s", async (action) => {
  proposal.actions = { can_decide: true, can_cancel: true };
  override = async (request) => {
    if (request.method === "PUT" && /\/(decision|cancellation)$/.test(request.url)) {
      proposal = {
        ...proposal,
        state: action === "reject" ? "rejected" : "cancelled",
        actions: { can_decide: false, can_cancel: false },
      };
      return json(proposal);
    }
  };
  await mount(<MarketplaceDetailDialog marketplaceSpaceId={catalogue} proposalId="proposal-1" onClose={() => {}} />);
  await ready(action);
  await click(action);
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(button(action)).toBeUndefined();
    expect(document.body.textContent).toContain(
      `rework.localMarketplace.states.${action === "reject" ? "rejected" : "cancelled"}`,
    );
  });
});

it("keeps the selected listing when correcting a rejected update proposal", async () => {
  override = async (request) =>
    request.method === "POST" && request.url.endsWith("/proposals")
      ? json({ code: "invalid_request", detail: "Invalid proposal" }, 422)
      : undefined;
  await mount(<MarketplaceProposalDialog source={source} onClose={() => {}} />);
  await ready("submit");
  await choose("proposalTarget", "entry-1");
  await click("submit");
  await ready("correctRequest");
  await click("correctRequest");
  await ready("submit");
  expect(
    (document.querySelector('select[aria-label="rework.localMarketplace.proposalTarget"]') as HTMLSelectElement).value,
  ).toBe("entry-1");
});

it("reconciles an uncertain older installation without silently installing the new publication", async () => {
  let updated = false;
  override = async (request) => {
    if (request.url.endsWith("/installations") && !updated) throw new TypeError("Accepted, response lost");
    if (updated && request.url.endsWith("/entries/entry-1"))
      return json({ ...snapshot, proposal_id: "proposal-2", display_name: "New publication" });
  };
  const detail = <MarketplaceDetailDialog marketplaceSpaceId={catalogue} entryId="entry-1" onClose={() => {}} />;
  await mount(detail);
  await vi.waitFor(() => expect(document.querySelector('option[value="destination"]')).not.toBeNull());
  await choose("destination", "destination");
  await ready("install");
  await click("install");
  await ready("retry");
  updated = true;
  await reload(detail);
  await ready("retry");
  expect(document.body.textContent).toContain("rework.localMarketplace.earlierInstallation");
  expect(button("install")).toBeUndefined();
  await click("retry");
  await vi.waitFor(() => expect(document.body.textContent).toContain("rework.localMarketplace.openResource"));
  const sent = writes("/installations");
  expect(sent).toHaveLength(2);
  expect(sent[1].headers.get("Idempotency-Key")).toBe(sent[0].headers.get("Idempotency-Key"));
  expect(await sent[1].json()).toEqual(await sent[0].json());
  expect(sessionStorage.length).toBe(0);
});

it("clears an acknowledged request even when its dialog unmounted before completion", async () => {
  const completion = deferredResponse();
  override = async (request) =>
    request.method === "POST" && request.url.endsWith("/proposals") ? completion.promise : undefined;
  await mount(<MarketplaceProposalDialog source={source} onClose={() => {}} />);
  await ready("submit");
  await click("submit");
  await vi.waitFor(() => expect(writes("/proposals")).toHaveLength(1));
  expect(sessionStorage.length).toBe(1);
  await mount(<></>);
  await act(async () => completion.resolve(json(proposal)));
  await vi.waitFor(() => expect(sessionStorage.length).toBe(0));
});
