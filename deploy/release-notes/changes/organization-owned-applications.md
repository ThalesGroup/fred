---
schema: 1
title: "Dedicate application and KB services to their owning organization"
impact: major
configuration: production
configuration_reason: "KB worker and credential bindings move from platform.knowledge_bases configuration to organization-owned SQL registrations; the generated Fred chart schema removes that option."
---
## Applicability

Fresh Weaver installations using hosted applications or Knowledge Bases. Swift is unchanged.

## Prerequisites

Deploy trusted application UI/API services independently of Fred, once per organization with separate credentials and storage. Their UI assets
and runtime configuration must use relative paths, because the browser directory
is now `/apps/<registration-uuid>/`. The SDK logical name remains unchanged.

## Configuration

The organization Owner opens Profile menu > Administration > Features > Apps,
registers service destinations and authorizes use. The platform Applications page
and `/platform/applications` routes are removed. The registry API is now
`/organizations/{organization_id}/applications` and requires organization Manage.
Technical administrator roles alone cannot register applications.

Remove `platform.knowledge_bases` from configuration. Register dedicated collectors
through Features > Knowledge Bases before installing their chart. The existing
SDK publish hook and run command are retained. Follow the
[operations procedure](../../../docs/architecture/08-operations.md#organization-owned-applications-and-knowledge-bases).

## Upgrade

Migrations 0056-0058 require an owning organization and scope logical-name uniqueness to it. Application HTTP origins are exclusive
to one organization. KB services reserve a dedicated workload identity per organization. Weaver supports fresh installations only; no ownership backfill or upgrade
of an existing global registry is provided. Never reset shared data as part of
this change. A populated local installation needs a separately agreed data plan.
Deploy the matching frontend and Control Plane together. Rebuild application UIs
that hardcode the old static browser path; the evaluator adaptation is in its repository.

## Validation

As an organization Owner, register and authorize an application in Features > Apps.
Check that a different organization sees only its own registrations, including
when it uses the same logical name. Check technical administrator and Member
access is denied, and that revocation blocks new application admissions.

## Rollback

Do not run older Control Plane code against the changed registry schema. Restore
a matching database/application backup through an explicitly approved procedure.

## Limitations

Static assets remain public and credential-free. Applications are trusted code,
not sandboxed third-party content. SQL/HTTP and component tests do not constitute
k3d or integration-platform browser acceptance. An alternate DNS name does not establish deployment isolation.
