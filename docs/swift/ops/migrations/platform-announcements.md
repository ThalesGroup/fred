---
schema: 1
title: "Replace configured info banners with admin-managed announcements"
impact: minor
configuration: production
configuration_reason: "platform.frontend.info_banner is removed from the control-plane configuration and generated Helm schema; deployments using it must remove it from their overlays and recreate the message in the admin UI."
---

## Applicability

All deployments require the new control-plane database migration. Deployments
using the old info banner also need to recreate their message. Existing documents
do not need re-ingestion.

## Prerequisites

Back up the control-plane database and retain the previous banner configuration.
A platform administrator with can_manage_platform is needed to create announcements.

## Configuration

Remove platform.frontend.info_banner from control-plane configuration and the
corresponding applications.control-plane-backend.configuration.platform.frontend.info_banner
Helm overlay. Keep upload_warning unchanged. No replacement configuration key
is required: announcements are managed at /admin/annonces.

## Upgrade

1. Apply control-plane migrations through b88202b8451e before starting the updated
   backend and frontend. Use your existing database migration procedure; the Helm
   migration hook is disabled by default.
2. Deploy the matching Fred backend and frontend. The new announcement table is
   initially empty; old banners are not imported automatically. Newly created
   announcements are disabled by default.
3. If a banner is needed, recreate its localized text and links in /admin/annonces,
   choose its severity and dismissal behavior, then enable it.

## Validation

Confirm the database migration succeeded and the admin page loads. Enable an
announcement and check that a signed-in user sees it after refreshing the page.
Check its translations, links and dismissal behavior before leaving it enabled.

## Rollback

Restore the previous Fred version and its saved info_banner configuration.
Announcements created in the new UI are not converted back. Back up their content
before any database downgrade: downgrading this revision drops the announcement
table and its data.

## Limitations

Announcements appear only in the authenticated application, not on login,
terms-acceptance or bootstrap screens. The old custom color and automatic hiding
options have no direct equivalent; severity controls color and users can dismiss
announcements when allowed. An existing open session refreshes announcements
every 60 seconds or on window focus.
