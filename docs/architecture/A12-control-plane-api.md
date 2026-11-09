# Control Plane REST inventory

One row per registered operation, grouped by URL prefix, to review naming and API
consistency. Routes are generated from the same OpenAPI contract as the frontend
client. Authentication does not grant content access: see the [SSI matrices](A7-action-role-matrix.md).

Full request/response types and status codes remain in OpenAPI. Generate the contract
with `make -C apps/control-plane generate-openapi` (`apps/control-plane/openapi.json`);
the [generated TypeScript client](../../apps/frontend/src/slices/controlPlane/controlPlaneOpenApi.ts)
provides a versioned view. Regenerate this inventory with `make -C docs/architecture generate-models`.

<!-- generated: openapi-index apps/control-plane/openapi.json -->
Paths are relative to `/control-plane/v1`.

Operations: [`/admin`](#admin-routes) · [`/agents`](#agents-routes) · [`/authorize`](#authorize-routes) · [`/bootstrap`](#bootstrap-routes) · [`/capability-preparations`](#capability-preparations-routes) · [`/deletions`](#deletions-routes) · [`/document-processing`](#document-processing-routes) · [`/document-uploads`](#document-uploads-routes) · [`/documents`](#documents-routes) · [`/folders`](#folders-routes) · [`/frontend`](#frontend-routes) · [`/gcu`](#gcu-routes) · [`/healthz`](#healthz-routes) · [`/import-export`](#import-export-routes) · [`/me`](#me-routes) · [`/organizations`](#organizations-routes) · [`/powerpoint-uploads`](#powerpoint-uploads-routes) · [`/skills`](#skills-routes) · [`/spaces`](#spaces-routes) · [`/users`](#users-routes).

## /admin routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/admin/organizations` | `organization_registry` | Required |
| POST | `/admin/organizations` | `create_organization` | Required |
| GET | `/admin/organizations/candidates` | `search_organization_candidates` | Required |
| GET | `/admin/organizations/{id}` | `get_organization` | Required |
| PATCH | `/admin/organizations/{id}` | `update_organization` | Required |
| GET | `/admin/teams` | `team_registry` | Required |

## /agents routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| POST | `/agents/execute/stream` | `execute_stream` | Required |
| GET | `/agents/sessions/{session_id}/messages` | `messages` | Required |

## /authorize routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| POST | `/authorize/document` | `authorize_document` | Required |
| POST | `/authorize/platform` | `authorize_platform` | Required |
| POST | `/authorize/scope` | `authorize_scope` | Required |
| POST | `/authorize/space` | `authorize_space` | Required |

## /bootstrap routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| POST | `/bootstrap/platform-admin` | `bootstrap_platform_admin` | Required |

## /capability-preparations routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/capability-preparations/cleanup` | `capability_preparation_cleanup` | Required |
| GET | `/capability-preparations/worker` | `capability_preparation_worker` | Required |
| GET | `/capability-preparations/{id}` | `capability_preparation_context` | Required |
| POST | `/capability-preparations/{id}/cleaned` | `capability_preparation_cleaned` | Required |
| POST | `/capability-preparations/{id}/confirm` | `capability_preparation_confirm` | Required |
| GET | `/capability-preparations/{id}/content` | `capability_preparation_content` | Required |

## /deletions routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/deletions/{operation_id}` | `deletion_status` | Required |

## /document-processing routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/document-processing/cleanup` | `cleanup` | Required |
| POST | `/document-processing/cleanup` | `cleaned` | Required |
| GET | `/document-processing/retrievable/{id}` | `retrieval_work` | Required |
| POST | `/document-processing/retrievable/{id}` | `confirm_retrievable` | Required |
| POST | `/document-processing/{id}/abandon` | `abandon` | Required |
| POST | `/document-processing/{id}/claim` | `claim` | Required |
| POST | `/document-processing/{id}/commit` | `commit` | Required |
| GET | `/document-processing/{id}/original` | `original` | Required |
| POST | `/document-processing/{id}/vectors` | `vectors` | Required |
| GET | `/document-processing/{id}/work` | `work` | Required |
| POST | `/document-processing/{id}/writes` | `writes` | Required |

## /document-uploads routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/document-uploads/{id}` | `receipt` | Required |
| PUT | `/document-uploads/{id}/acknowledgment` | `acknowledge` | Required |

## /documents routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| DELETE | `/documents/{id}` | `delete_document` | Required |
| GET | `/documents/{id}/content` | `content` | Required |
| GET | `/documents/{id}/preview` | `preview` | Required |
| GET | `/documents/{id}/processing` | `history` | Required |
| POST | `/documents/{id}/processing` | `start` | Required |
| PUT | `/documents/{id}/retrievable` | `set_retrievable` | Required |

## /folders routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| POST | `/folders` | `create_folder` | Required |
| PATCH | `/folders/{id}` | `rename_folder` | Required |
| DELETE | `/folders/{id}` | `delete_folder` | Required |
| POST | `/folders/{id}/documents` | `upload` | Required |
| POST | `/folders/{id}/documents/preflight` | `preflight` | Required |

## /frontend routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/frontend/config` | `frontend_config` | Public |

## /gcu routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| POST | `/gcu` | `accept_terms` | Required |

## /healthz routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/healthz` | `health` | Public |

## /import-export routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| POST | `/import-export/import` | `import_blueprint` | Required |

## /me routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/me` | `me` | Required |
| GET | `/me/marketplace-proposal-spaces` | `marketplace_proposal_spaces` | Required |
| GET | `/me/marketplaces` | `marketplaces` | Required |
| GET | `/me/onboarding` | `onboarding_status` | Required |
| POST | `/me/personal-space` | `create_personal_space` | Required |
| GET | `/me/spaces` | `my_spaces` | Required |
| GET | `/me/usage` | `my_usage` | Required |

## /organizations routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/organizations/{organization_id}/agents` | `organization_agents` | Required |
| PUT | `/organizations/{organization_id}/agents/{agent_id}/default-on` | `set_organization_agent_default` | Required |
| GET | `/organizations/{organization_id}/capabilities` | `organization_capabilities` | Required |
| POST | `/organizations/{organization_id}/capabilities/{runtime_id}/refresh` | `refresh_organization_capabilities` | Required |
| PUT | `/organizations/{organization_id}/capabilities/{runtime_id}/{capability_id}/default-on` | `set_organization_capability_default` | Required |
| GET | `/organizations/{organization_id}/capabilities/{runtime_id}/{capability_id}/revoke-impact` | `organization_capability_revoke_impact` | Required |
| GET | `/organizations/{organization_id}/model-policy` | `organization_model_policy` | Required |
| PUT | `/organizations/{organization_id}/model-policy` | `replace_organization_model_policy` | Required |
| POST | `/organizations/{organization_id}/model-sources/{source_id}/refresh` | `refresh_model_source` | Required |
| GET | `/organizations/{organization_id}/models` | `organization_models` | Required |
| GET | `/organizations/{organization_id}/supervision` | `organization_supervision` | Required |
| GET | `/organizations/{organization_id}/supervision/teams/{team_id}` | `team_supervision` | Required |

## /powerpoint-uploads routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/powerpoint-uploads/{request_key}` | `powerpoint_upload_receipt` | Required |

## /skills routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/skills/defaults` | `default_skills` | Required |

## /spaces routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| POST | `/spaces` | `create_space` | Required |
| DELETE | `/spaces/{id}` | `delete_space` | Required |
| GET | `/spaces/{id}/document-uploads` | `receipts` | Required |
| GET | `/spaces/{id}/entries` | `entries` | Required |
| GET | `/spaces/{id}/member-candidates` | `space_member_candidates` | Required |
| GET | `/spaces/{id}/members` | `space_members` | Required |
| PUT | `/spaces/{id}/roles/{role}/{user}` | `grant` | Required |
| DELETE | `/spaces/{id}/roles/{role}/{user}` | `revoke` | Required |
| GET | `/spaces/{id}/storage` | `summary` | Required |
| GET | `/spaces/{marketplace_space_id}/marketplace/entries` | `marketplace_entries` | Required |
| GET | `/spaces/{marketplace_space_id}/marketplace/entries/{entry_id}` | `marketplace_entry` | Required |
| POST | `/spaces/{marketplace_space_id}/marketplace/entries/{entry_id}/installations` | `install_marketplace_entry` | Required |
| PUT | `/spaces/{marketplace_space_id}/marketplace/entries/{entry_id}/withdrawal` | `withdraw_marketplace_entry` | Required |
| GET | `/spaces/{marketplace_space_id}/marketplace/proposals` | `marketplace_proposals` | Required |
| POST | `/spaces/{marketplace_space_id}/marketplace/proposals` | `submit_marketplace_proposal` | Required |
| GET | `/spaces/{marketplace_space_id}/marketplace/proposals/{proposal_id}` | `marketplace_proposal` | Required |
| PUT | `/spaces/{marketplace_space_id}/marketplace/proposals/{proposal_id}/cancellation` | `cancel_marketplace_proposal` | Required |
| PUT | `/spaces/{marketplace_space_id}/marketplace/proposals/{proposal_id}/decision` | `decide_marketplace_proposal` | Required |
| GET | `/spaces/{space_id}/agent-instances` | `list_agent_instances` | Required |
| POST | `/spaces/{space_id}/agent-instances` | `create_agent_instance` | Required |
| GET | `/spaces/{space_id}/agent-instances/{agent_instance_id}` | `get_agent_instance` | Required |
| PATCH | `/spaces/{space_id}/agent-instances/{agent_instance_id}` | `update_agent_instance` | Required |
| DELETE | `/spaces/{space_id}/agent-instances/{agent_instance_id}` | `delete_agent_instance` | Required |
| POST | `/spaces/{space_id}/agent-instances/{agent_instance_id}/prepare-execution` | `prepare_execution` | Required |
| GET | `/spaces/{space_id}/agent-instances/{agent_instance_id}/runtime` | `resolve_runtime` | Required |
| POST | `/spaces/{space_id}/agent-instances/{agent_instance_id}/runtime` | `admit_runtime` | Required |
| GET | `/spaces/{space_id}/agent-templates` | `space_agent_templates` | Required |
| GET | `/spaces/{space_id}/capability-policies` | `space_capability_policies` | Required |
| PUT | `/spaces/{space_id}/capability-policies/{runtime_id}` | `replace_space_capability_policy` | Required |
| GET | `/spaces/{space_id}/marketplace-installations/{installation_id}` | `marketplace_installation` | Required |
| GET | `/spaces/{space_id}/powerpoint-template` | `resolve_powerpoint_template` | Required |
| PUT | `/spaces/{space_id}/powerpoint-template` | `upload_powerpoint_template` | Required |
| DELETE | `/spaces/{space_id}/powerpoint-template` | `remove_powerpoint_template` | Required |
| POST | `/spaces/{space_id}/powerpoint-template/prepare` | `rerun_powerpoint_template` | Required |
| GET | `/spaces/{space_id}/powerpoint-template/settings` | `get_powerpoint_settings` | Required |
| PUT | `/spaces/{space_id}/powerpoint-template/settings` | `put_powerpoint_settings` | Required |
| GET | `/spaces/{space_id}/powerpoint-template/{file_id}/content` | `download_powerpoint_template` | Required |
| GET | `/spaces/{space_id}/prompt-categories` | `list_prompt_categories` | Required |
| POST | `/spaces/{space_id}/prompt-categories` | `create_prompt_category` | Required |
| PATCH | `/spaces/{space_id}/prompt-categories/{category_id}` | `rename_prompt_category` | Required |
| DELETE | `/spaces/{space_id}/prompt-categories/{category_id}` | `delete_prompt_category` | Required |
| GET | `/spaces/{space_id}/prompts` | `list_prompts` | Required |
| POST | `/spaces/{space_id}/prompts` | `create_prompt` | Required |
| GET | `/spaces/{space_id}/prompts/{prompt_id}` | `get_prompt` | Required |
| PATCH | `/spaces/{space_id}/prompts/{prompt_id}` | `update_prompt` | Required |
| DELETE | `/spaces/{space_id}/prompts/{prompt_id}` | `delete_prompt` | Required |
| PUT | `/spaces/{space_id}/prompts/{prompt_id}/favorite` | `add_prompt_favorite` | Required |
| DELETE | `/spaces/{space_id}/prompts/{prompt_id}/favorite` | `remove_prompt_favorite` | Required |
| GET | `/spaces/{space_id}/sessions` | `list_sessions` | Required |
| POST | `/spaces/{space_id}/sessions` | `create_session` | Required |
| GET | `/spaces/{space_id}/sessions/{session_id}` | `get_session` | Required |
| PATCH | `/spaces/{space_id}/sessions/{session_id}` | `update_session` | Required |
| DELETE | `/spaces/{space_id}/sessions/{session_id}` | `delete_session` | Required |
| GET | `/spaces/{space_id}/sessions/{session_id}/attachments` | `list_attachments` | Required |
| POST | `/spaces/{space_id}/sessions/{session_id}/attachments` | `upload_attachment` | Required |
| DELETE | `/spaces/{space_id}/sessions/{session_id}/attachments/{document_id}` | `delete_attachment` | Required |
| GET | `/spaces/{space_id}/sessions/{session_id}/attachments/{document_id}/content` | `download_attachment` | Required |
| POST | `/spaces/{space_id}/sessions/{session_id}/exchanges/{exchange_id}/usage` | `record_usage` | Required |
| GET | `/spaces/{space_id}/sessions/{session_id}/files` | `list_conversation_files` | Required |
| POST | `/spaces/{space_id}/sessions/{session_id}/files` | `write_conversation_file` | Required |
| GET | `/spaces/{space_id}/sessions/{session_id}/files/write-target` | `file_write_target` | Required |
| GET | `/spaces/{space_id}/sessions/{session_id}/files/{document_id}/content` | `download_conversation_file` | Required |
| GET | `/spaces/{space_id}/sessions/{session_id}/files/{document_id}/preview` | `preview_conversation_file` | Required |
| POST | `/spaces/{space_id}/sessions/{session_id}/generated-title` | `record_title` | Required |
| GET | `/spaces/{space_id}/skills` | `list_skills` | Required |
| POST | `/spaces/{space_id}/skills` | `create_skill` | Required |
| POST | `/spaces/{space_id}/skills/packages/{name}/install` | `install_skill` | Required |
| GET | `/spaces/{space_id}/skills/scope` | `skill_scope` | Required |
| GET | `/spaces/{space_id}/skills/scope/{skill_id}` | `preview_skill` | Required |
| GET | `/spaces/{space_id}/skills/{skill_id}` | `get_skill` | Required |
| PUT | `/spaces/{space_id}/skills/{skill_id}` | `put_skill` | Required |
| DELETE | `/spaces/{space_id}/skills/{skill_id}` | `delete_skill` | Required |
| GET | `/spaces/{space_id}/usage` | `space_usage` | Required |
| GET | `/spaces/{space_id}/wiki/availability` | `wiki_availability` | Required |
| GET | `/spaces/{space_id}/wiki/pages` | `wiki_pages` | Required |
| POST | `/spaces/{space_id}/wiki/pages` | `create_wiki_page` | Required |
| GET | `/spaces/{space_id}/wiki/pages/{page_id}` | `wiki_page` | Required |
| PATCH | `/spaces/{space_id}/wiki/pages/{page_id}` | `patch_wiki_page` | Required |
| DELETE | `/spaces/{space_id}/wiki/pages/{page_id}` | `delete_wiki_page` | Required |
| PUT | `/spaces/{space_id}/wiki/pages/{page_id}/content` | `write_wiki_page` | Required |
| POST | `/spaces/{space_id}/wiki/pages/{page_id}/review` | `set_wiki_review_mark` | Required |
| GET | `/spaces/{space_id}/wiki/pages/{page_id}/revisions` | `wiki_revisions` | Required |
| POST | `/spaces/{space_id}/wiki/pages/{page_id}/revisions/{revision_id}/restore` | `restore_wiki_revision` | Required |
| POST | `/spaces/{space_id}/wiki/proposals/edit` | `propose_wiki_edit` | Required |
| POST | `/spaces/{space_id}/wiki/proposals/page` | `propose_wiki_page` | Required |
| GET | `/spaces/{space_id}/wiki/proposals/{proposal_id}` | `wiki_proposal` | Required |
| POST | `/spaces/{space_id}/wiki/proposals/{proposal_id}/publish` | `publish_wiki_proposal` | Required |
| GET | `/spaces/{space_id}/wiki/rules` | `wiki_rules` | Required |
| PUT | `/spaces/{space_id}/wiki/rules` | `write_wiki_rules` | Required |

## /users routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/users/me/preferences` | `get_my_preferences` | Required |
| PATCH | `/users/me/preferences` | `patch_my_preferences` | Required |
| GET | `/users/platform-roles` | `list_platform_roles` | Required |
| PUT | `/users/{user}/platform-roles/{role}` | `grant_platform_role` | Required |
| DELETE | `/users/{user}/platform-roles/{role}` | `revoke_platform_role` | Required |
<!-- end generated -->
