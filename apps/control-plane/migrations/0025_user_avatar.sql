-- Copyright Thales 2026
-- SPDX-License-Identifier: Apache-2.0

-- Personal display data: the verified subject is text, as in users_preferences.
-- user_identity is a directory cache, not an account authority or a suitable FK.
-- Objects use the existing installation-owned S3 namespace and cleanup inventory.
create table user_avatar (
    id uuid primary key,
    user_id text not null check (btrim(user_id) <> ''),
    object_key text not null unique,
    size bigint not null check (size between 1 and 262144),
    status text not null check (status in ('pending', 'active', 'retired')),
    expires_at timestamptz not null
);
create unique index user_avatar_active on user_avatar(user_id) where status = 'active';
create unique index user_avatar_pending on user_avatar(user_id) where status = 'pending';
create index user_avatar_owner on user_avatar(user_id) where status <> 'retired';
create index user_avatar_cleanup on user_avatar(expires_at, id) where status <> 'active';

-- Pending writes cannot publish after expiry or retirement. Account erasure must
-- retire the subject's rows alongside users_preferences; no organization owns them.
