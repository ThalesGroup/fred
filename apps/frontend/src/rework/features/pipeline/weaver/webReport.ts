// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import type { WebProbe } from "../scenarios/webResearchScenario";
import { assert } from "./resourceSupport";

const EXPECTED = `scheme_file scheme_ftp scheme_gopher scheme_javascript credentials_in_url port_alternate
port_internal_service whitespace_in_url focus_with_offset search_over_limit loopback_ipv4 localhost unspecified
private_10 private_172 private_192 shared_cgnat cloud_metadata loopback_ipv6 ipv4_mapped nat64 six_to_four
unique_local_ipv6 decimal_ip hex_ip platform_keycloak platform_postgres cluster_api engine_scheme_file
engine_credentials engine_port dns_to_loopback redirect_to_loopback redirect_to_metadata redirect_to_file
redirect_chain binary_content safesearch_on safesearch_moderate safesearch_off safesearch_policy search_ceiling
fetch_public fetch_focus`.split(/\s+/);

export function verifyWebProbes(probes: WebProbe[]) {
  assert(
    probes.every(
      (probe) =>
        probe &&
        typeof probe.id === "string" &&
        ["schema", "guard", "remote", "search", "fetch"].includes(probe.group) &&
        ["passed", "failed", "skipped"].includes(probe.verdict) &&
        typeof probe.title === "string" &&
        typeof probe.expected === "string" &&
        typeof probe.observed === "string" &&
        (probe.detail == null || typeof probe.detail === "string"),
    ),
    "The web diagnostic contains malformed probes.",
  );
  const ids = new Set(probes.map((probe) => probe.id));
  assert(ids.size === probes.length, "The web diagnostic contains duplicate probes.");
  assert(
    EXPECTED.every((id) => ids.has(id)),
    "The web diagnostic is incomplete; not all fixed probes returned an outcome.",
  );
}
