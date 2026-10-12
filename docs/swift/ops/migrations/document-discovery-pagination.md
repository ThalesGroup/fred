---
schema: 1
title: "Filter, sort and paginate document discovery"
impact: none
configuration: none
configuration_reason: "Discovery extends existing authenticated tree APIs; no production configuration or permission-default changes are required."
no_action_reason: "No data migration, index migration or re-ingestion is needed; stored documents retain their existing arrival timestamps."
---

## Applicability

Deployments using document_access and the Knowledge Flow document-tree route.

## Prerequisites

Deploy compatible Knowledge Flow and runtime versions together so new tool arguments are accepted by the backend.

## Configuration

No new configuration keys or permission defaults apply. The existing character budget remains 20,000 by default and at most 60,000.

## Upgrade

Deploy normally. No metadata backfill, re-ingestion or operator migration command is required.

## Validation

Ask for a filename/title match and the latest known addition. Confirm the tool uses descending arrival order with a limit of one, and exposes continuation for larger pages. Tool details retain metadata hover and show a discreet continuation footer. An invalid cursor requests a restart; a document exceeding the budget requests a larger budget or narrower folder.

## Rollback

Roll back the applications normally. Requests without a page limit and historical stored traces remain readable; stored documents are unchanged.

## Limitations

Paging traverses a live corpus, not a cross-request snapshot. Unknown arrivals require qualified latest-known results. A page that cannot fit one complete compact document record and its required path returns a budget error. Query filtering/sorting can scan matching SQL rows; metadata hydration and model output are bounded by page size and character budget.
