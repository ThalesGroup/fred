# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""One pure router over the complete Weaver turn snapshot."""

from fred_sdk.contracts.weaver import ModelOfferKey, RuntimeModelOffer, RuntimeModels

from .contracts import ModelRoutingError, ModelSelectionSource


class ModelRoutingResolver:
    def __init__(self, models: RuntimeModels):
        self.models = models
        self.offers = {offer.key: offer for offer in models.offers}

    def resolve(
        self, choice: ModelOfferKey | None
    ) -> tuple[RuntimeModelOffer, ModelSelectionSource]:
        models = self.models
        if models.requires_reselection and choice is None:
            raise ModelRoutingError(
                "Legacy model profile requires explicit offer re-selection"
            )
        key = choice or models.recommendation or models.policy.default
        source = (
            ModelSelectionSource.USER_CHOICE
            if choice is not None
            else ModelSelectionSource.INSTANCE_RECOMMENDATION
            if models.recommendation is not None
            else ModelSelectionSource.DEFAULT
        )
        offer = self.offers.get(key) if key is not None else None
        if offer is None or not offer.permitted:
            raise ModelRoutingError(
                "Selected model is absent or forbidden; no substitution is allowed"
            )
        if offer.candidate:
            return offer, source
        # A stale discovery failure alone never proves withdrawal. A disabled or
        # unobserved source, missing metadata or revoked offer cannot trigger fallback.
        if "withdrawn" not in offer.diagnostics or any(
            d not in {"withdrawn", "discovery_unavailable"} for d in offer.diagnostics
        ):
            raise ModelRoutingError("Selected model is unavailable")
        fallback = (
            self.offers.get(models.policy.fallback) if models.policy.fallback else None
        )
        if fallback is None or not fallback.permitted or not fallback.candidate:
            raise ModelRoutingError(
                "Confirmed withdrawal has no permitted usable fallback"
            )
        return fallback, ModelSelectionSource.WITHDRAWAL_FALLBACK
