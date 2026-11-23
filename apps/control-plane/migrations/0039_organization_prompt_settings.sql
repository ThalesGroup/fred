-- Execution instructions are organization settings, never prompt-library resources.
create table organization_prompt_settings (
    organization_id uuid primary key references space(id) on delete cascade,
    common_text text check (char_length(common_text) <= 20000),
    common_updated_by text,
    common_updated_at timestamptz,
    creation_text text check (char_length(creation_text) between 1 and 20000 and creation_text ~ '[^[:space:]]'),
    creation_model_source_id text collate "C",
    creation_model_upstream_id text collate "C",
    check ((creation_model_source_id is null) = (creation_model_upstream_id is null)),
    foreign key (creation_model_source_id,creation_model_upstream_id)
        references model_offer(source_id,upstream_model_id),
    creation_reasoning boolean not null default false,
    creation_text_updated_by text,
    creation_text_updated_at timestamptz,
    creation_updated_by text,
    creation_updated_at timestamptz,
    check ((common_text is null) = (common_updated_at is null)),
    check ((common_updated_by is null) = (common_updated_at is null)),
    check ((creation_text_updated_by is null) = (creation_text_updated_at is null)),
    check ((creation_updated_by is null) = (creation_updated_at is null))
);
create trigger organization_prompt_settings_organization before insert or update of organization_id
    on organization_prompt_settings for each row execute function require_organization_space();
comment on trigger organization_prompt_settings_organization on organization_prompt_settings is
    'assertion: consistency - execution prompt settings belong to an organization';
