#!/usr/bin/env python3
# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Submit one ingestion request mixing processing profiles, for local testing.

Why this exists: the upload endpoint carries a single profile for the whole
submission, so the UI cannot produce the case this is meant to exercise — several
`rich` documents ahead of `fast` ones inside *one* parent workflow. The scheduler
endpoint already accepts a profile per file, so this drives that existing path
rather than adding anything to the product.

It does not upload: it submits documents that are already in the catalog, which
is what `/process-documents` takes. Upload them first, however you normally would,
then pass their uids here.

Usage:
    python submit_mixed_profiles.py \
        --url http://localhost:8111/knowledge-flow/v1 \
        --token "$FRED_TOKEN" \
        --tag <tag-id> \
        rich:<uid> rich:<uid> rich:<uid> fast:<uid> fast:<uid>

Every argument is `<profile>:<document_uid>`, in the order they should be
submitted. Prints the workflow id, which is what to open in the Temporal UI.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

PROFILES = ("fast", "medium", "rich")


def _parse_document(raw: str) -> dict:
    profile, _, document_uid = raw.partition(":")
    if profile not in PROFILES or not document_uid:
        raise argparse.ArgumentTypeError(f"expected <{'|'.join(PROFILES)}>:<document_uid>, got {raw!r}")
    return {"profile": profile, "document_uid": document_uid}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="Knowledge Flow base url, e.g. http://localhost:8111/knowledge-flow/v1")
    parser.add_argument("--token", required=True, help="Bearer token for the API")
    parser.add_argument("--tag", required=True, help="Tag id carried by every file; the endpoint authorizes against it")
    parser.add_argument("--source-tag", default="fred")
    parser.add_argument("--pipeline-name", default="mixed-profiles-local-test")
    parser.add_argument("documents", nargs="+", type=_parse_document, metavar="PROFILE:DOCUMENT_UID")
    args = parser.parse_args()

    files = [
        {
            "source_tag": args.source_tag,
            "tags": [args.tag],
            "document_uid": document["document_uid"],
            "display_name": document["document_uid"],
            "profile": document["profile"],
        }
        for document in args.documents
    ]
    payload = json.dumps({"files": files, "pipeline_name": args.pipeline_name}).encode()

    request = urllib.request.Request(
        f"{args.url.rstrip('/')}/process-documents",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {args.token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:  # noqa: S310 - a local URL the operator typed
            body = json.loads(response.read())
    except urllib.error.HTTPError as error:
        print(f"HTTP {error.code}: {error.read().decode(errors='replace')}", file=sys.stderr)
        return 1

    order = ", ".join(f"{document['profile']}" for document in args.documents)
    print(f"submitted {len(files)} document(s) in order: {order}")
    print(f"workflow_id: {body.get('workflow_id')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
