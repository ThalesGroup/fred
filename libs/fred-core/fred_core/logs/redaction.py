# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0

"""Target known credential-bearing URL patterns without discarding diagnostics."""

import re

_SENSITIVE_QUERY_PARAM_RE = re.compile(
    r"([?&](?:token|access_token|id_token|person|run|agent)=)[^&\s\"]+",
    re.IGNORECASE,
)


def sanitize_sensitive_query_params(value: str) -> str:
    value = re.sub(
        r"((?:/platform-access/free/|/join/))[^/?\s\"]+", r"\1<redacted>", value
    )
    return _SENSITIVE_QUERY_PARAM_RE.sub(r"\1<redacted>", value)
