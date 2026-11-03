# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for details.

import base64

from fred_core.logs.context import log_context
from fred_core.logs.propagation import (
    decode_log_context,
    encode_log_context,
    outbound_context_headers,
)


def test_transport_accepts_bounded_json_and_rejects_unsafe_or_ambiguous_envelopes():
    values = {"custom": [True, None, {"step": 2}], "correlation_id": "journey"}
    encoded = encode_log_context(values)
    assert encoded is not None
    assert decode_log_context(encoded) == (values, None)
    assert encode_log_context({"custom": object()}) is None
    assert encode_log_context({"custom": "x" * 1025}) is None
    assert encode_log_context({str(i): i for i in range(33)}) is None
    assert encode_log_context({"custom": [[[[1]]]]}) is None
    assert encode_log_context({"custom": ["x" * 1024] * 4}) is None
    assert encode_log_context({"authorization": "credential-canary"}) is None
    assert encode_log_context({"custom": float("nan")}) is None
    assert encode_log_context({"custom": 2**63}) is None
    for payload in (
        b'{"v":2,"context":{}}',
        b'{"v":true,"context":{}}',
        b'{"v":1,"context":{"id":1,"id":2}}',
        b'{"v":1,"context":{"custom":NaN}}',
        b'{"v":1,"context":{"token":"credential-canary"}}',
        b"x" * 4097,
    ):
        values, reason = decode_log_context(
            base64.urlsafe_b64encode(payload).decode().rstrip("=")
        )
        assert values is None and reason is not None
    assert decode_log_context("a" * 8193) == (None, "oversized")
    with log_context(custom="bound"):
        headers = outbound_context_headers()
    # Only the bound bag is exported. An event-only extra is never part of it.
    assert decode_log_context(next(iter(headers.values()))) == (
        {"custom": "bound"},
        None,
    )
