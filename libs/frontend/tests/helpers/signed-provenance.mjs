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
