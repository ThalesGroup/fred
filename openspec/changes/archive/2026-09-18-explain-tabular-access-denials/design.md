# Design

## Context

See proposal.md. Current swift adds attachment ownership resolution and regression coverage absent from the original POC patch.

## Goals / Non-Goals

Preserve every access check and attachment branch. Do not alter APIs, schemas, ingestion, or storage.

## Decisions

Reuse one message builder at all four dataset-denial sites, including direct dataset reads added upstream. It interpolates only caller-supplied identifiers; no metadata or existence lookup is added. Keep upstream tests and port source tests alongside them, covering filenames, SQL aliases, forbidden UIDs, and the controller's 403 detail. Duplicated literals were rejected because recovery guidance would drift.

## Risks / Trade-offs

A forbidden UID remains intentionally ambiguous. The listing tool resolves only documents already visible to the caller; no permission grant is implied.
