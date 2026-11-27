# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

import json

from fred_runtime.app.conversation_trace_masking import mask_http, mask_model, mask_sse


def _session_event(event: dict[str, object], *, outgoing: bool = False):
    return mask_sse(
        b"event: message\r\ndata: " + json.dumps(event).encode() + b"\r\n\r\n",
        outgoing=outgoing,
    )


def test_mistral_native_reasoning_keeps_blocks_and_usage():
    evidence = _session_event(
        {
            "object": "chat.completion.chunk",
            "p": "provider padding",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "thinking",
                                "thinking": [
                                    {"type": "text", "text": "private reasoning"}
                                ],
                                "closed": True,
                            }
                        ],
                    },
                    "finish_reason": None,
                }
            ],
            "usage": {
                "total_tokens": 30,
                "completion_tokens_details": {"reasoning_tokens": 8},
            },
        }
    )

    assert evidence.data == {
        "object": "chat.completion.chunk",
        "choices": [
            {
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": [{"type": "text", "text": "<redacted>"}],
                            "closed": True,
                        }
                    ],
                },
                "finish_reason": None,
            }
        ],
        "usage": {
            "total_tokens": 30,
            "completion_tokens_details": {"reasoning_tokens": 8},
        },
    }
    assert [(item.key, item.position) for item in evidence.annotations] == [("p", 1)]


def test_c3_preserves_usage_and_timing_and_masks_prompt_token_ids():
    evidence = _session_event(
        {
            "choices": [{"index": 0, "delta": {"reasoning": "private C3 thought"}}],
            "usage": {
                "prompt_tokens": 31,
                "prompt_tokens_details": {"cached_tokens": 12},
            },
            "metrics": {
                "time_to_first_token_ms": 1.5,
                "queue_time_ms": 2,
                "generation_time_ms": 7,
                "mean_itl_ms": 1,
                "tokens_per_second": 23.75,
                "new_diagnostic": "secret",
            },
            "prompt_text": "private C3 prompt",
            "prompt_token_ids": [190, 542],
        }
    )

    assert evidence.data == {
        "choices": [{"index": 0, "delta": {"reasoning": "<redacted>"}}],
        "usage": {"prompt_tokens": 31, "prompt_tokens_details": {"cached_tokens": 12}},
        "metrics": {
            "time_to_first_token_ms": 1.5,
            "queue_time_ms": 2,
            "generation_time_ms": 7,
            "mean_itl_ms": 1,
            "tokens_per_second": 23.75,
        },
        "prompt_text": "<redacted>",
    }
    assert [item.key for item in evidence.annotations] == ["prompt_token_ids"]


def test_azure_responses_keeps_reviewed_filter_codes_masks_raw_and_annotates_new_field():
    evidence = _session_event(
        {
            "type": "response.completed",
            "sequence_number": 5,
            "response": {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "private answer"}],
                    }
                ],
                "content_filters": [
                    {
                        "blocked": False,
                        "source_type": "input",
                        "content_filter_results": {
                            "hate": {"filtered": False, "severity": "safe"},
                            "user@example.org": {"filtered": True},
                        },
                        "content_filter_raw": {
                            "user@example.org": "private raw detail"
                        },
                    }
                ],
                "new_filter_schema": {"user@example.org": True},
                "usage": {"input_tokens": 14, "output_tokens": 3},
            },
        }
    )

    assert evidence.data == {
        "type": "response.completed",
        "sequence_number": 5,
        "response": {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "<redacted>"}],
                }
            ],
            "content_filters": [
                {
                    "blocked": False,
                    "source_type": "input",
                    "content_filter_results": {
                        "hate": {"filtered": False, "severity": "safe"}
                    },
                }
            ],
            "usage": {"input_tokens": 14, "output_tokens": 3},
        },
    }
    assert [
        (item.parent, item.key, item.value_type) for item in evidence.annotations
    ] == [
        (["response", "content_filters", 0], "content_filter_raw", "object"),
        (["response"], "new_filter_schema", "object"),
    ]
    assert "user@example.org" not in evidence.model_dump_json()


def test_http_tool_arguments_keep_parse_status_and_linkage_without_values():
    evidence = mask_http(
        json.dumps(
            {
                "input": [
                    {
                        "type": "function_call",
                        "call_id": "abc",
                        "arguments": '{"private key": true}',
                    },
                    {"type": "function_call", "call_id": "null", "arguments": "oops"},
                    {
                        "type": "function_call_output",
                        "call_id": "abc",
                        "output": "private result",
                    },
                ],
                "unknown": {"user@example.org": "private"},
            }
        ).encode(),
        request=True,
        remote_tool=False,
    )

    assert evidence.data == {
        "input": [
            {"type": "function_call", "call_id": "call_1", "arguments": "<redacted>"},
            {"type": "function_call", "call_id": "null", "arguments": "<redacted>"},
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": "<redacted>",
            },
        ],
    }
    assert [(item.key, item.invalid_json) for item in evidence.annotations] == [
        ("arguments", False),
        ("arguments", True),
    ]
    assert "unknown" not in evidence.model_dump_json()


def test_langchain_omits_args_and_masks_diagnostics():
    evidence = mask_model(
        {
            "input": {
                "messages": [
                    {
                        "role": "assistant",
                        "tool_calls": [{"id": "abc", "args": {"private key": 1}}],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "abc",
                        "content": "private result",
                    },
                ]
            },
            "output": {
                "messages": [
                    {"invalid_tool_calls": [{"id": "null", "error": "private error"}]}
                ]
            },
        }
    )

    assert evidence.data == {
        "input": {
            "messages": [
                {"role": "assistant", "tool_calls": [{"id": "call_1"}]},
                {"role": "tool", "tool_call_id": "call_1", "content": "<redacted>"},
            ]
        },
        "output": {"messages": [{"invalid_tool_calls": [{"id": "null"}]}]},
    }
    assert [(item.key, item.value_type) for item in evidence.annotations] == [
        ("args", "object"),
        ("error", "string"),
    ]


def test_remote_tool_http_and_malformed_data_have_no_raw_fallback():
    assert (
        mask_http(
            b'{"metrics":{"tokens_per_second":4242}}', request=False, remote_tool=True
        ).data
        == "<redacted>"
    )
    assert mask_http(
        b"private malformed data", request=True, remote_tool=False
    ).unavailable
    assert mask_sse(b"data: {private", outgoing=False).unavailable
    assert mask_sse(b"data: [DONE]\n\n", outgoing=False).data == "[DONE]"
    assert _session_event(
        {"kind": "assistant_delta", "text": "private"}, outgoing=True
    ).data == {
        "kind": "assistant_delta",
        "text": "<redacted>",
    }
