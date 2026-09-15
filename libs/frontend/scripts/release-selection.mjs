import assert from "node:assert/strict";

import { validateReleaseContract } from "./release-contract.mjs";

// A missing option keeps the existing all-member development commands. An
// explicitly empty option is different: it must not silently pack everything.
export function selectReleaseMembers(contract, selection) {
  validateReleaseContract(contract);
  return selectInventoryMembers({
    inventory: contract.inventory,
    packages: contract.packages,
    selection,
  });
}

export function selectInventoryMembers({ inventory, packages, selection }) {
  const members = inventory.members;
  const ids = members.map(({ id }) => id);
  if (selection === undefined)
    return orderInventoryMembers({ inventory, packages, selectedIds: ids });
  assert.equal(
    typeof selection,
    "string",
    "package selection must be a string",
  );
  assert(selection.trim(), "package selection must not be empty");
  const requested = selection.split(",").map((id) => id.trim());
  assert(
    requested.every(Boolean),
    "package selection contains an empty member",
  );
  assert.equal(
    new Set(requested).size,
    requested.length,
    "duplicate package selection",
  );
  for (const id of requested)
    assert(ids.includes(id), `unregistered or private package selection ${id}`);
  return orderInventoryMembers({ inventory, packages, selectedIds: requested });
}

// Publication order follows declared member dependencies/peers. It does not
// infer dependencies from the current names or assume exactly three packages.
export function orderReleaseMembers(contract, selectedIds) {
  validateReleaseContract(contract);
  return orderInventoryMembers({
    inventory: contract.inventory,
    packages: contract.packages,
    selectedIds,
  });
}

export function orderInventoryMembers({ inventory, packages, selectedIds }) {
  assert(
    Array.isArray(selectedIds) && selectedIds.length > 0,
    "selected members are required",
  );
  assert.equal(
    new Set(selectedIds).size,
    selectedIds.length,
    "duplicate selected member",
  );
  const inventoryIds = inventory.members.map(({ id }) => id);
  for (const id of selectedIds)
    assert(inventoryIds.includes(id), `unregistered selected member ${id}`);
  const selected = new Set(selectedIds);
  const ordered = [];
  const visiting = new Set();
  function visit(id) {
    if (ordered.includes(id)) return;
    assert(!visiting.has(id), `cyclic release dependency at ${id}`);
    visiting.add(id);
    const manifest = packages[id].expectedManifest;
    const dependencies = {
      ...manifest.dependencies,
      ...manifest.peerDependencies,
    };
    for (const member of inventory.members)
      if (
        selected.has(member.id) &&
        member.id !== id &&
        dependencies[packages[member.id].name]
      )
        visit(member.id);
    visiting.delete(id);
    ordered.push(id);
  }
  for (const id of inventoryIds) if (selected.has(id)) visit(id);
  return ordered;
}

export function selectionOption(argv = process.argv) {
  const positions = argv.flatMap((arg, index) =>
    arg === "--select" ? [index] : [],
  );
  assert(positions.length <= 1, "duplicate --select option");
  if (positions.length === 0) return undefined;
  const value = argv[positions[0] + 1];
  assert(
    value !== undefined && !value.startsWith("--"),
    "--select requires package IDs",
  );
  return value;
}
