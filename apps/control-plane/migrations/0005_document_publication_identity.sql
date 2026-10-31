-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Carry the document identity through the processing -> generation -> publication
-- chain so foreign keys enforce it, including concurrent writes and purges.
alter table generation add column document_id uuid;
update generation g set document_id = p.document_id
    from document_processing p where p.id = g.processing_id;
alter table generation alter column document_id set not null;

alter table document_processing add constraint document_processing_id_document_key
    unique (id, document_id);
alter table generation drop constraint generation_processing_id_fkey;
alter table generation add constraint generation_processing_document_fkey
    foreign key (processing_id, document_id)
    references document_processing (id, document_id) on delete cascade;

alter table generation add constraint generation_id_document_key unique (id, document_id);
alter table document drop constraint document_published_generation_fkey;
-- A purge can still delete processing/generations before deleting the document
-- in the same transaction. A surviving document cannot retain a dangling pointer.
alter table document add constraint document_published_generation_fkey
    foreign key (published_generation, id) references generation (id, document_id)
    deferrable initially deferred;
