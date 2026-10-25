-- Display choices belong to the verified subject, independently of membership.
-- user_identity is a best-effort UUID directory, not an authoritative account table.
CREATE TABLE users_preferences (
    user_id text PRIMARY KEY,
    ui_theme_id text CHECK (ui_theme_id ~ '^[a-z][a-z0-9-]{0,31}$'),
    theme_mode text NOT NULL DEFAULT 'system' CHECK (theme_mode IN ('light', 'dark', 'system')),
    language text CHECK (language IN ('en', 'fr')),
    sidebar_collapsed boolean NOT NULL DEFAULT false,
    team_sort_mode text NOT NULL DEFAULT 'recent' CHECK (team_sort_mode IN ('recent', 'alpha')),
    agent_sort text NOT NULL DEFAULT 'name' CHECK (agent_sort IN ('name', 'created_at:desc', 'updated_at:desc')),
    updated_at timestamptz NOT NULL DEFAULT now()
);
