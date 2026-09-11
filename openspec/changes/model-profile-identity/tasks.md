## 1. Model identity

- [x] 1.1 Add optional `ModelProfile.model_id` with a blank-value validator, and
      `ModelProfile.capability_id` as the one derivation of the model's id.
- [x] 1.2 Group and id `/agents/models-catalog` entries by the profile's identity
      instead of `(provider, model.name)`.
- [x] 1.3 Carry the winning profile's identity on `ModelSelection.capability_id`,
      keeping `model_capability_id(provider, name)` for a platform binding.
- [x] 1.4 Gate `usable_model_ids` and `reasoning_enabled_model_ids` in
      `build_for_chat` on that field instead of re-deriving it.

## 2. Coverage and docs

- [x] 2.1 Cover the projection: two profiles sharing a wire name split by
      `model_id`, the same two without it still merge, and mixed declaration does
      not merge.
- [x] 2.2 Cover `build_for_chat`: a gateway sibling is authorized and reasons by
      its own identity, never its sibling's.
- [x] 2.3 Cover the contract: blank `model_id` rejected, `capability_id` with and
      without the field.
- [x] 2.4 Pin the "no control-plane change needed" decision: given already-split
      pod entries sharing a wire name, `resolve_effective_chat_model` reads the
      entry owning the winning profile.
- [x] 2.5 Update `RUNTIME-EXECUTION-CONTRACT.md` §8.78 and the
      `LLM_ROUTING_FRED.md` pod author guide, including the upgrade note.
- [x] 2.6 Run `make code-quality` and `make test` in fred-runtime and
      control-plane-backend.
