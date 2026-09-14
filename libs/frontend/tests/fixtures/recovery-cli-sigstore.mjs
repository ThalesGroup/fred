import assert from "node:assert/strict";
import { verify as verifySignature } from "node:crypto";

export async function verify(bundle, options) {
  assert.equal(
    bundle.fixtureCertificateIdentityURI,
    options.certificateIdentityURI,
    "controlled provenance workflow differs",
  );
  assert.equal(
    bundle.fixtureCertificateIssuer,
    options.certificateIssuer,
    "controlled provenance issuer differs",
  );
  assert.equal(
    verifySignature(
      null,
      Buffer.from(bundle.dsseEnvelope.payload),
      bundle.fixturePublicKey,
      Buffer.from(bundle.dsseEnvelope.signatures[0].sig, "base64"),
    ),
    true,
    "controlled provenance signature is invalid",
  );
}
