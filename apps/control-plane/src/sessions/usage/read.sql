-- The authorized caller supplies scoped ($1); $2/$3 bound [since, until), $4 is hour/day/week.
-- $5 bounds each ranking including its truncation sentinel; $6 is the maintained factor catalog.
-- $7 is the working organization for self, or the team-expansion flag for collective reads. Scans are bounded by statement_timeout.
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
), token_facts as (
    select w.*, date_trunc($4, w.occurred_at, 'UTC') as start,
        case when p.session_id is null then t.first_at end as first_at
    from windowed w join turn_starts t using (session_id, exchange_id)
    left join prior_turns p using (session_id, exchange_id)
), factors as (
    select t.*, coalesce($6::jsonb->'models'->upstream_model_id, $6::jsonb->'models'->'default') as factor,
        not ($6::jsonb->'models' ? upstream_model_id) as fallback
    from token_facts t
), facts as (
    -- Cache reads are a subset of input; creation tokens remain fresh input, never added again.
    -- A missing/zero required coefficient makes this report unavailable for that measure.
    select f.*,
        case when input_tokens = 0 and output_tokens = 0 then 0
            else (input_tokens::numeric + output_tokens) / 1000
                * nullif((factor->>'co2e_grams_per_1k_tokens')::numeric, 0)
        end as co2e,
        case when input_tokens = 0 and output_tokens = 0 then 0
            else (input_tokens::numeric + output_tokens) / 1000
                * nullif((factor->>'kwh_per_1k_tokens')::numeric, 0)
        end as energy,
        case when input_tokens = 0 and output_tokens = 0 then 0 else (
            (case when input_tokens = least(cache_read_tokens, input_tokens) then 0
                else (input_tokens::numeric - least(cache_read_tokens, input_tokens))
                    * nullif((factor->>'cost_per_1k_input_tokens')::numeric, 0) end)
            + (case when cache_read_tokens = 0 then 0
                else least(cache_read_tokens, input_tokens)::numeric
                    * nullif((factor->>'cost_per_1k_cached_input_tokens')::numeric, 0) end)
            + (case when output_tokens = 0 then 0
                else output_tokens::numeric
                    * nullif((factor->>'cost_per_1k_output_tokens')::numeric, 0) end)
        ) / 1000 / ($6::jsonb->>'usd_per_eur')::numeric end as cost
    from factors f
), aggregates as (
    select start, agent_instance_id, space_id, model_source_id, upstream_model_id,
        case when grouping(start) = 1 then
            count(distinct (session_id, exchange_id)) filter (where first_at is not null)
        else
            count(distinct (session_id, exchange_id)) filter (
                where start = date_trunc($4, first_at, 'UTC'))
        end as recorded_exchanges,
        coalesce(sum(input_tokens), 0) as input_tokens,
        coalesce(sum(output_tokens), 0) as output_tokens,
        coalesce(sum(cache_read_tokens), 0) as cache_read_tokens,
        coalesce(sum(cache_creation_tokens), 0) as cache_creation_tokens,
        jsonb_build_object(
            'usage.cost_eur', jsonb_build_object(
                'value', case when count(*) = 0 then '0' else sum(cost)::text end,
                'coverage', case when count(*) = count(cost) then 'complete'
                    when count(cost) = 0 then 'unavailable' else 'partial' end,
                'fallback', coalesce(bool_or(fallback and (input_tokens > 0 or output_tokens > 0)), false)),
            'usage.co2e_grams', jsonb_build_object(
                'value', case when count(*) = 0 then '0' else sum(co2e)::text end,
                'coverage', case when count(*) = count(co2e) then 'complete'
                    when count(co2e) = 0 then 'unavailable' else 'partial' end,
                'fallback', coalesce(bool_or(fallback and (input_tokens > 0 or output_tokens > 0)), false)),
            'usage.energy_kwh', jsonb_build_object(
                'value', case when count(*) = 0 then '0' else sum(energy)::text end,
                'coverage', case when count(*) = count(energy) then 'complete'
                    when count(energy) = 0 then 'unavailable' else 'partial' end,
                'fallback', coalesce(bool_or(fallback and (input_tokens > 0 or output_tokens > 0)), false))
        ) as estimates
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
        0::bigint, 0::bigint, 0::bigint, 0::bigint, 0::bigint,
        '{"usage.cost_eur":{"value":"0","coverage":"complete","fallback":false},"usage.co2e_grams":{"value":"0","coverage":"complete","fallback":false},"usage.energy_kwh":{"value":"0","coverage":"complete","fallback":false}}'::jsonb
    from buckets b where not exists (select 1 from aggregates a where a.start = b.start)
), ranked as (
    select *, row_number() over (
        partition by case when agent_instance_id is not null then 'agent'
                          when model_source_id is not null then 'model' else 'other' end
        order by (input_tokens + output_tokens) desc,
                 agent_instance_id, space_id, model_source_id, upstream_model_id
    ) as rank
    from complete
), bounded as (
    select * from ranked
    where (agent_instance_id is null and model_source_id is null) or rank <= $5
), latest_names as (
    select distinct on (s.agent_instance_id) s.agent_instance_id, s.agent_display_name
    from session_metadata s
    join (select distinct agent_instance_id from bounded where agent_instance_id is not null) used using (agent_instance_id)
    left join agent_instance a using (agent_instance_id)
    where a.agent_instance_id is null
    order by s.agent_instance_id, s.updated_at desc, s.created_at desc, s.session_id desc
)
select c.start, c.agent_instance_id, c.space_id, c.model_source_id, c.upstream_model_id,
    c.recorded_exchanges::text, c.input_tokens::text, c.output_tokens::text,
    c.cache_read_tokens::text, c.cache_creation_tokens::text,
    (c.input_tokens + c.output_tokens)::text as total_tokens,
    coalesce(a.display_name, n.agent_display_name) as display_name, c.estimates
from bounded c
left join agent_instance a using (agent_instance_id)
left join latest_names n using (agent_instance_id)
order by c.start asc nulls last,
    (c.input_tokens::numeric + c.output_tokens::numeric) desc,
    c.agent_instance_id, c.space_id, c.model_source_id, c.upstream_model_id
