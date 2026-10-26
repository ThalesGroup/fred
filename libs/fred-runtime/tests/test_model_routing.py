# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Weaver routing regression cases; Swift pod profile/catalog cases retired."""

from fred_runtime.model_routing.resolver import ModelRoutingResolver


class TestModelRoutingResolver:
    def test_resolver_uses_only_the_supplied_snapshot(self) -> None:
        from weaver_fixtures import resolved_binding

        models = resolved_binding().models
        resolver = ModelRoutingResolver(models)
        assert resolver.resolve(None)[0].key == models.recommendation
        assert resolver.resolve(models.policy.fallback)[0].key == models.policy.fallback
