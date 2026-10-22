-- One active personal space per owner and organization; retired rows do not count.
create unique index space_personal_owner on space (organization_id, personal_owner)
    where personal_owner is not null and deletion_id is null;
