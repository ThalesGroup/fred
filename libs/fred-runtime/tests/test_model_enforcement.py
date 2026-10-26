# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Prepared Weaver selection cases. Replaces Swift's profile/bypass assertions."""

import pytest
from fred_runtime.model_routing.contracts import ModelRoutingError, ModelSelectionSource
from fred_runtime.model_routing.resolver import ModelRoutingResolver
from fred_sdk.contracts.weaver import ModelOfferKey
from weaver_fixtures import resolved_binding


def test_explicit_choice_wins_over_recommendation_and_default():
    models = resolved_binding().models
    offer, source = ModelRoutingResolver(models).resolve(models.policy.fallback)
    assert offer.key == models.policy.fallback
    assert source == ModelSelectionSource.USER_CHOICE


def test_recommendation_then_organization_default():
    models = resolved_binding(default="second").models
    assert ModelRoutingResolver(models).resolve(None)[0].key == models.recommendation
    models = models.model_copy(update={"recommendation": None})
    assert ModelRoutingResolver(models).resolve(None)[0].key == models.policy.default


def test_forbidden_explicit_choice_never_substitutes():
    models = resolved_binding(
        permitted=False, candidate=False, diagnostics=("not_permitted",)
    ).models
    with pytest.raises(ModelRoutingError):
        ModelRoutingResolver(models).resolve(models.recommendation)


def test_unknown_choice_never_substitutes():
    with pytest.raises(ModelRoutingError):
        ModelRoutingResolver(resolved_binding().models).resolve(
            ModelOfferKey(source_id="foreign", upstream_model_id="first")
        )


def test_no_arbitrary_first_default():
    models = resolved_binding().models
    models = models.model_copy(
        update={
            "recommendation": None,
            "policy": models.policy.model_copy(update={"default": None}),
        }
    )
    with pytest.raises(ModelRoutingError):
        ModelRoutingResolver(models).resolve(None)


def test_confirmed_withdrawal_uses_only_authorized_fallback():
    models = resolved_binding(candidate=False, diagnostics=("withdrawn",)).models
    offer, source = ModelRoutingResolver(models).resolve(None)
    assert offer.key == models.policy.fallback
    assert source == ModelSelectionSource.WITHDRAWAL_FALLBACK
    denied = models.offers[1].model_copy(
        update={"candidate": False, "permitted": False}
    )
    models = models.model_copy(update={"offers": (models.offers[0], denied)})
    with pytest.raises(ModelRoutingError):
        ModelRoutingResolver(models).resolve(None)


@pytest.mark.parametrize(
    "reason",
    [
        "source_disabled",
        "source_revision_unobserved",
        "discovery_unavailable",
        "not_permitted",
        "unknown_offer",
    ],
)
def test_unavailability_is_not_withdrawal(reason):
    models = resolved_binding(candidate=False, diagnostics=(reason,)).models
    with pytest.raises(ModelRoutingError):
        ModelRoutingResolver(models).resolve(None)


def test_legacy_profile_requires_reselection():
    models = resolved_binding().models.model_copy(
        update={
            "legacy_profile_id": "old",
            "requires_reselection": True,
            "recommendation": None,
        }
    )
    with pytest.raises(ModelRoutingError):
        ModelRoutingResolver(models).resolve(None)
    assert (
        ModelRoutingResolver(models).resolve(models.policy.default)[0].key
        == models.policy.default
    )
