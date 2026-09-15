export async function resolve(specifier, context, nextResolve) {
  if (specifier === "sigstore")
    return {
      shortCircuit: true,
      url: new URL("./recovery-cli-sigstore.mjs", import.meta.url).href,
    };
  return nextResolve(specifier, context);
}
