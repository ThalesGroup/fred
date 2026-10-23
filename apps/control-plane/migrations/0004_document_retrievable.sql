-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
ALTER TABLE document ADD COLUMN retrievable boolean NOT NULL DEFAULT false;
ALTER TABLE document ADD COLUMN retrieval_command jsonb;
ALTER TABLE document ADD COLUMN retrievable_pending boolean GENERATED ALWAYS AS
    (retrieval_command IS NOT NULL AND NOT (retrieval_command->>'confirmed')::boolean) STORED;
-- Previously published documents are restored explicitly from verified artifacts,
-- never inferred searchable from their processing status or vector count.
