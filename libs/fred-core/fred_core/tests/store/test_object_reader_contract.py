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

"""Every fred-core content store must be usable as an object-proxy reader.

`ContentStore` deliberately stays a two-method write/URL protocol
(CONTENT-URL-STRATEGY RFC §5), so the object proxy takes the store through the
separate `ObjectReader` interface and the app wires it with a `cast`. That cast is
only safe while every implementation really does read — which is what this pins.
"""

from __future__ import annotations

import inspect

import pytest

from fred_core.store import GcsContentStore, LocalContentStore, MinioContentStore

_STORES = [LocalContentStore, MinioContentStore, GcsContentStore]


@pytest.mark.parametrize("store_class", _STORES, ids=lambda cls: cls.__name__)
def test_store_implements_the_object_reader_interface(store_class: type) -> None:
    for method in ("stat_object", "get_object_stream"):
        assert callable(getattr(store_class, method, None)), (
            f"{store_class.__name__}.{method} is missing"
        )

    parameters = inspect.signature(store_class.get_object_stream).parameters
    assert {"key", "start", "length"} <= set(parameters)


@pytest.mark.parametrize("store_class", _STORES, ids=lambda cls: cls.__name__)
def test_stat_object_returns_the_metadata_the_proxy_needs(store_class: type) -> None:
    annotation = inspect.signature(store_class.stat_object).return_annotation
    assert "ObjectInfo" in str(annotation)
