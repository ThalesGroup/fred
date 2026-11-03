-- The caller supplies scoped ($1); $2/$3 bound [since, until), $4 is hour/day/week.
, windowed as materialized (
    select * from scoped where occurred_at >= $2 and occurred_at < $3
), turn_starts as (
    select session_id, exchange_id, min(occurred_at) as first_at
    from windowed group by session_id, exchange_id
), prior_turns as (
    -- Only prior consumption of exchanges present in the requested range matters.
    -- This preserves the first-consumption rule across range boundaries as well as HITL resumes.
    select distinct s.session_id, s.exchange_id
    from scoped s join turn_starts t using (session_id, exchange_id)
    where s.occurred_at < $2
), facts as (
    select w.*, date_trunc($4, w.occurred_at, 'UTC') as start,
        case when p.session_id is null then t.first_at end as first_at
    from windowed w join turn_starts t using (session_id, exchange_id)
    left join prior_turns p using (session_id, exchange_id)
), aggregates as (
    select start, agent_instance_id, space_id, model_source_id, upstream_model_id,
        case when grouping(start) = 1 then
            count(distinct (session_id, exchange_id)) filter (where first_at is not null)
        else
            count(distinct (session_id, exchange_id)) filter (
                where start = date_trunc($4, first_at, 'UTC'))
        end as turns,
        coalesce(sum(input_tokens), 0)::bigint as input_tokens,
        coalesce(sum(output_tokens), 0)::bigint as output_tokens,
        coalesce(sum(cache_read_tokens), 0)::bigint as cache_read_tokens,
        coalesce(sum(cache_creation_tokens), 0)::bigint as cache_creation_tokens
    from facts
    group by grouping sets ((), (start), (agent_instance_id, space_id), (model_source_id, upstream_model_id))
), buckets as (
    -- Timestamp without zone makes stepping independent of the connection timezone/DST.
    select bucket at time zone 'UTC' as start
    from generate_series(date_trunc($4, $2::timestamptz at time zone 'UTC'),
                         $3::timestamptz at time zone 'UTC', ('1 ' || $4)::interval) bucket
    where bucket at time zone 'UTC' < $3
), complete as (
    select * from aggregates
    union all
    select b.start, null::uuid, null::uuid, null::text, null::text,
        0::bigint, 0::bigint, 0::bigint, 0::bigint, 0::bigint
    from buckets b where not exists (select 1 from aggregates a where a.start = b.start)
), latest_names as (
    select distinct on (s.agent_instance_id) s.agent_instance_id, s.agent_display_name
    from session_metadata s
    join (select distinct agent_instance_id from windowed) used using (agent_instance_id)
    left join agent_instance a using (agent_instance_id)
    where a.agent_instance_id is null
    order by s.agent_instance_id, s.updated_at desc, s.created_at desc, s.session_id desc
)
select c.*, coalesce(a.display_name, n.agent_display_name) as display_name
from complete c
left join agent_instance a using (agent_instance_id)
left join latest_names n using (agent_instance_id)
order by c.start asc nulls last,
    (c.input_tokens::numeric + c.output_tokens::numeric) desc,
    c.agent_instance_id, c.space_id, c.model_source_id, c.upstream_model_id
