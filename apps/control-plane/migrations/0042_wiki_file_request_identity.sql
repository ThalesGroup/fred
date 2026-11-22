-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Fresh installations only. Request identity belongs to the upload receipt, not
-- the current source bytes or a Wiki revision that may already have been deleted.
set local lock_timeout = '5s';

alter table document_upload add column request_fingerprint text;
alter table document_upload add constraint document_upload_request_fingerprint check (
    (purpose = 'wiki') = (request_fingerprint is not null)
    and (request_fingerprint is null or request_fingerprint ~ '^[0-9a-f]{64}$'));

create function protect_upload_request_fingerprint() returns trigger language plpgsql as $$
begin
    raise exception 'upload request identity is immutable' using errcode = '23514',
        constraint = TG_NAME, table = TG_TABLE_NAME;
end $$;
create trigger document_upload_request_immutable before update on document_upload
    for each row when (old.request_fingerprint is distinct from new.request_fingerprint)
    execute function protect_upload_request_fingerprint();
comment on trigger document_upload_request_immutable on document_upload is
    'assertion: immutability - Wiki file request identity survives proposal deletion';
