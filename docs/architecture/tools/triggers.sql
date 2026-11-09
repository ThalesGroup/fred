-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0
-- Run in the same disposable database as tbls, after every migration.
select coalesce(json_agg(catalogue), '[]'::json) from (
    select c.relname as "table", t.tgname as "trigger", p.proname as "function",
        concat(case when t.tgtype & 2 <> 0 then 'BEFORE'
                    when t.tgtype & 64 <> 0 then 'INSTEAD OF' else 'AFTER' end, ' ',
            concat_ws(' OR ',
                case when t.tgtype & 4 <> 0 then 'INSERT' end,
                case when t.tgtype & 16 <> 0 then 'UPDATE' end,
                case when t.tgtype & 8 <> 0 then 'DELETE' end,
                case when t.tgtype & 32 <> 0 then 'TRUNCATE' end),
            case when t.tgtype & 1 <> 0 then ' / ROW' else ' / STATEMENT' end) as "when",
        obj_description(t.oid, 'pg_trigger') as comment
    from pg_trigger t
    join pg_proc p on p.oid=t.tgfoid
    join pg_class c on c.oid=t.tgrelid
    join pg_namespace n on n.oid=c.relnamespace
    where not t.tgisinternal and n.nspname='control_plane'
    order by c.relname,t.tgname
) catalogue;
