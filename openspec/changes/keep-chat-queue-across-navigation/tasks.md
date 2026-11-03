## 1. Implementation

- [x] 1.1 Own pending messages by session in the existing tab registry; retain them on navigation and drain only in the open conversation.
- [x] 1.2 Apply detached steering delivery and clear only the owning queue on interruption, Stop or deletion.

## 2. Verification and close-out

- [ ] 2.1 Cover navigation/remount, completion, detached delivery, real cuts, deletion and reattachment without background sends; run focused tests and root quality.
- [ ] 2.2 Review the cumulative PR and the new delta independently; reconcile existing docs, sync the spec, archive the change and open the separate PR above #3418 for issue #3427.
