# 3. Security

Fred separates identity, admission and permission. This chapter explains access
to organizations, spaces, documents and managed conversations through Control Plane.

## 3.1. Signing in is not permission

```mermaid
flowchart TB
    identity["Who are you?<br/>Sign in"] --> consent["Have you accepted the terms?<br/>When required"]
    consent --> rights["May you perform this action<br/>in this space?"]

    classDef default fill:#F1F5F9,stroke:#64748B,color:#0F172A
```

The configured identity provider authenticates the person. Each person accepts
their own terms of use when required. Neither step creates membership or content
rights. Every protected action is checked by the server; a visible UI control is
not an authorization.

## 3.2. Governance and content access

Fred separates technical administration from business work.

- An **admin** is technical. The platform admin creates organizations and names
  their admin and initial owner; the organization admin names and replaces the
  organization's owners and reads supervision aggregates. Neither reads content
  or shapes the business structure. There is no team or project admin.
- An **owner** (French: *responsable*) manages a space and its community: its
  members, its resources and its sub-spaces. The organization owner also manages
  model choices and creates teams; a team owner creates projects. Each creation
  names the new space's owner; the creator receives no role there.
- Reading or contributing to content requires a content role: **member** reads,
  **editor** reads and writes, **analyst** reads and evaluates. Owner alone grants
  no content access.

One person may hold several roles; nothing currently prevents an admin from also
being an owner. The [roles annex](A11-roles.md) is the reference for
responsibilities, effective permissions, attribution rules and the gaps to examine
in security reviews.

## 3.3. Where rights apply

```mermaid
flowchart TB
    organization["Organization"] --> team["Team"]
    team --> project["Project"]

    classDef default fill:#F1F5F9,stroke:#64748B,color:#0F172A
```

**A role applies only to the space where it is granted.** No role reaches a child
space. Léa, an editor of Acme, does not see the Research team; Elena, an analyst
of Research, does not see its Atlas project. Roles held at several levels are
independent: Carol reads Research and edits Atlas.

To hold a role on a team or project, a person first needs a direct content role
on its parent. This prerequisite grants nothing on the child. In the other
direction, a search from a space may include its ancestors' common resources, but
only those the person can read through a direct role on that ancestor.

A person may hold roles in several organizations; each one is reached only through
the roles held there. Folders and documents use their owning space's permissions. **Personal spaces inherit no content rights** from the
organization or teams. Any business role (owner, member, editor or analyst) on an
active organization, team or project lets a person open their own personal space;
an admin role alone does not. Losing the last business role hides and closes
access to the personal space without deleting its data.

## 3.4. Rights remain current

Reads and writes use current permissions. For document processing, the worker's
service identity does not replace the initiating user's authority: original
access and publication recheck that user's rights. A committed revocation during
upload prevents publication; an already authorized read may finish.

The [technical security annex](A6-security.md) describes authentication,
service identities and enforcement. The [action and role matrix](A7-action-role-matrix.md)
provides exact permissions, conditions and implementation references.

## 3.5. Model permission and conversation access

Alice, Acme's organization owner, can authorize a model for Acme without being
allowed to read Bob's Research conversation. Oscar's organization-admin role
does not grant model-management permission. Bob needs access to the space and
permission to use its assistant;
Carol's membership in the same Research team lets her read its shared documents,
but does not open Bob's conversation. Selecting the same model never merges their
rights or conversations.

The browser's choice is a request, not authority. Fred verifies it on the server.
Each new turn acquires its authorized context; an admitted turn may finish with
that context after a policy change. Cancellation and run termination remain
separate controls. The [technical boundary](A6-security.md#managed-agent-turn-authority)
explains how the person's rights stay distinct from the pod's service identity.

## 3.6. Documents used by an assistant

An assistant reads documents on behalf of the person in the conversation, never
with broader rights. Using it requires a content role in its space. Its search
is limited to that space and the ancestors the person can read. From Research,
Bob's assistant also searches Acme because Bob is a member of Acme.

The vector index is not an authorization source. Each result is checked against
the document's current placement and publication before the model sees it.
Search rights follow the turn context; a role removed during a turn applies from
the next message. The [technical annex](A6-security.md#document-search-within-a-turn)
lists the checks and their implementation.
