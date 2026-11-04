-- Existing conversations never acquire automatic titles on upgrade. New sessions
-- explicitly opt in; the first admitted execution consumes eligibility once.
alter table session_metadata
    add column title_pending boolean not null default false,
    add column title_attempt uuid,
    add check (not title_pending or title_attempt is null);

alter table organization_model_policy
    add column title_source_id text collate "C",
    add column title_upstream_model_id text collate "C",
    add check ((title_source_id is null) = (title_upstream_model_id is null)),
    add foreign key (organization_id, title_source_id, title_upstream_model_id)
        references organization_model_permission (organization_id, source_id, upstream_model_id)
        deferrable initially deferred;
