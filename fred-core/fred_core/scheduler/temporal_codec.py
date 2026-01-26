# Copyright Thales 2025
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

from __future__ import annotations

import os
from typing import Iterable, Optional

from temporalio.api.common.v1 import Payload
from temporalio.converter import DataConverter, DefaultPayloadConverter, PayloadCodec

_ENCODING_KEY = "encoding"
_ORIGINAL_ENCODING_KEY = "orig-encoding"
_ENCRYPTED_ENCODING = b"binary/encrypted"


class FernetPayloadCodec(PayloadCodec):
    def __init__(self, key: bytes) -> None:
        from cryptography.fernet import Fernet

        self._fernet = Fernet(key)

    async def encode(self, payloads: Iterable[Payload]) -> list[Payload]:
        return [self._encode_payload(payload) for payload in payloads]

    async def decode(self, payloads: Iterable[Payload]) -> list[Payload]:
        return [self._decode_payload(payload) for payload in payloads]

    def _encode_payload(self, payload: Payload) -> Payload:
        metadata = dict(payload.metadata)
        if metadata.get(_ENCODING_KEY) == _ENCRYPTED_ENCODING:
            return payload

        data = payload.data or b""
        encrypted = self._fernet.encrypt(data)
        metadata[_ORIGINAL_ENCODING_KEY] = metadata.get(_ENCODING_KEY, b"")
        metadata[_ENCODING_KEY] = _ENCRYPTED_ENCODING
        return Payload(metadata=metadata, data=encrypted)

    def _decode_payload(self, payload: Payload) -> Payload:
        metadata = dict(payload.metadata)
        if metadata.get(_ENCODING_KEY) != _ENCRYPTED_ENCODING:
            return payload

        decrypted = self._fernet.decrypt(payload.data or b"")
        original_encoding = metadata.get(_ORIGINAL_ENCODING_KEY, b"")
        metadata[_ENCODING_KEY] = original_encoding
        metadata.pop(_ORIGINAL_ENCODING_KEY, None)
        return Payload(metadata=metadata, data=decrypted)


def build_temporal_data_converter_from_env(
    env_key: str = "FRED_TEMPORAL_CODEC_KEY",
) -> Optional[DataConverter]:
    key = os.getenv(env_key)
    if not key:
        return None
    codec = FernetPayloadCodec(key.encode())
    return DataConverter(
        payload_converter_class=DefaultPayloadConverter, payload_codec=codec
    )
