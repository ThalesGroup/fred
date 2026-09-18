import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";

import {
  verifyFixtureSignature,
  verifyProvenanceAttestation,
} from "../../scripts/registry-verifier.mjs";

export async function signedPublishingProvenance({
  artifactDigest,
  repository,
  sourceCommit,
  workflow,
  runId,
  runAttempt,
  certificateIssuer,
  signedStatementType = "https://in-toto.io/Statement/v1",
  signedPredicateType = "https://slsa.dev/provenance/v1",
}) {
  const [location, ref] = workflow.split("@");
  assert(
    location.startsWith(`${repository}/`),
    "fixture workflow repository differs",
  );
  const path = location.slice(repository.length + 1);
  const statement = {
    _type: signedStatementType,
    predicateType: signedPredicateType,
    subject: [{ digest: { sha512: artifactDigest.slice("sha512-".length) } }],
    predicate: {
      buildDefinition: {
        externalParameters: {
          workflow: { repository, path, ref },
        },
        resolvedDependencies: [
          {
            uri: `git+${repository}@${ref}`,
            digest: { gitCommit: sourceCommit },
          },
        ],
      },
      runDetails: {
        metadata: {
          invocationId: `${repository}/actions/runs/${runId}/attempts/${runAttempt}`,
        },
      },
    },
  };
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const payload = Buffer.from(JSON.stringify(statement)).toString("base64");
  const signature = sign(null, Buffer.from(payload), privateKey).toString(
    "base64",
  );
  return verifyProvenanceAttestation(
    {
      attestations: [
        {
          predicateType: "https://slsa.dev/provenance/v1",
          bundle: {
            dsseEnvelope: {
              payloadType: "application/vnd.in-toto+json",
              payload,
              signatures: [{ sig: signature }],
            },
          },
        },
      ],
    },
    {
      expectedWorkflow: workflow,
      expectedRepository: repository,
      certificateIssuer,
      verifyBundle: async (bundle, options) => {
        assert.deepEqual(options, {
          certificateIssuer,
          certificateIdentityURI: workflow,
        });
        assert.equal(
          verifyFixtureSignature({
            payload: bundle.dsseEnvelope.payload,
            signature: bundle.dsseEnvelope.signatures[0].sig,
            publicKey,
          }),
          true,
          "controlled provenance signature differs",
        );
      },
    },
  );
}
