import assert from "node:assert/strict";

const themeSelectors = new Map([
  ['[data-theme="light"]', "light"],
  ['[data-theme="dark"]', "dark"],
]);
const permittedSelectors = new Set([":root", ...themeSelectors.keys()]);

function normalizeCssString(value) {
  return value.trim().replace(/^(['"])(.*)\1$/, "$2");
}

function assertTokenRule(rule, sourceDescription) {
  const selectors = rule.selectors ?? [];
  assert.equal(
    selectors.length,
    1,
    `${sourceDescription} token rules must use one permitted selector`,
  );
  const selector = selectors[0].trim();
  assert(
    permittedSelectors.has(selector),
    `${sourceDescription} selector is not permitted: ${selector}`,
  );
  for (const node of rule.nodes ?? []) {
    if (node.type === "comment") continue;
    assert.equal(
      node.type,
      "decl",
      `${sourceDescription} ${selector} contains unsupported ${node.type}`,
    );
    if (node.prop.startsWith("--")) continue;
    const theme = themeSelectors.get(selector);
    assert(
      node.prop.toLowerCase() === "color-scheme" &&
        node.value.trim().toLowerCase() === theme,
      `${sourceDescription} ${selector} may declare only custom properties and its matching color-scheme, found ${node.prop}`,
    );
  }
}

function assertSpectrumProperty(atRule, sourceDescription) {
  assert.equal(
    atRule.params.trim(),
    "--angle",
    `${sourceDescription} permits only the reviewed @property --angle registration`,
  );
  const declarations = (atRule.nodes ?? []).filter(
    (node) => node.type !== "comment",
  );
  assert(
    declarations.every((node) => node.type === "decl"),
    `${sourceDescription} @property --angle contains unsupported content`,
  );
  assert.equal(
    declarations.length,
    3,
    `${sourceDescription} @property --angle must contain its three reviewed declarations`,
  );
  const values = Object.fromEntries(
    declarations.map((declaration) => [
      declaration.prop.toLowerCase(),
      normalizeCssString(declaration.value),
    ]),
  );
  assert.deepEqual(
    values,
    { syntax: "<angle>", "initial-value": "0deg", inherits: "false" },
    `${sourceDescription} @property --angle differs from the reviewed registration`,
  );
}

function assertForcedColorsMedia(atRule, sourceDescription) {
  assert.equal(
    atRule.params.trim().toLowerCase(),
    "(forced-colors: active)",
    `${sourceDescription} permits only the reviewed forced-colors media override`,
  );
  const rules = (atRule.nodes ?? []).filter((node) => node.type !== "comment");
  assert.equal(
    rules.length,
    1,
    `${sourceDescription} forced-colors override must contain one token rule`,
  );
  assert.equal(
    rules[0].type,
    "rule",
    `${sourceDescription} forced-colors override contains unsupported content`,
  );
  assertTokenRule(rules[0], sourceDescription);
  assert.equal(
    rules[0].selector.trim(),
    ":root",
    `${sourceDescription} forced-colors override must target :root`,
  );
}

export function assertNoCssImports(root, sourceDescription) {
  root.walkAtRules((atRule) => {
    assert.notEqual(
      atRule.name.toLowerCase(),
      "import",
      `${sourceDescription} must not contain @import`,
    );
  });
}

export function assertTokenCssContract(root, sourceDescription) {
  assertNoCssImports(root, sourceDescription);
  for (const node of root.nodes) {
    if (node.type === "comment") continue;
    if (node.type === "rule") {
      assertTokenRule(node, sourceDescription);
      continue;
    }
    assert.equal(
      node.type,
      "atrule",
      `${sourceDescription} contains unsupported top-level ${node.type}`,
    );
    const name = node.name.toLowerCase();
    if (name === "property") {
      assertSpectrumProperty(node, sourceDescription);
    } else if (name === "media") {
      assertForcedColorsMedia(node, sourceDescription);
    } else {
      assert.fail(
        `${sourceDescription} at-rule is not permitted: @${node.name}`,
      );
    }
  }
}
