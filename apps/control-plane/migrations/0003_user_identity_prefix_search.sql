-- Candidate search matches a case-insensitive prefix of each profile field.
create index user_identity_username_prefix on user_identity (lower(username) text_pattern_ops);
create index user_identity_email_prefix on user_identity (lower(email) text_pattern_ops);
create index user_identity_first_name_prefix on user_identity (lower(first_name) text_pattern_ops);
create index user_identity_last_name_prefix on user_identity (lower(last_name) text_pattern_ops);
