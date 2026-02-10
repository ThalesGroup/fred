---
name: fga
description: Query OpenFGA authorization tuples and explain why a user has (or doesn't have) a permission on an object
disable-model-invocation: true
user-invocable: true
allowed-tools: Bash, Read
argument-hint: <command> [args...]
---

# OpenFGA CLI Skill

You help the user query and debug their OpenFGA authorization model using the `fga` CLI.

## Connection setup

Always use these flags:

```
--api-url http://localhost:9080
--api-token Azerty123_
```

**Store ID**: Do NOT hardcode a store ID. Resolve it dynamically by running:

```bash
fga store list --api-url http://localhost:9080 --api-token Azerty123_ | jq -r '.stores[] | select(.name == "fred") | .id'
```

Use the returned ID as the `--store-id` value for all subsequent commands.

Store the three flags in a variable for convenience:

```bash
STORE_ID=$(fga store list --api-url http://localhost:9080 --api-token Azerty123_ | jq -r '.stores[] | select(.name == "fred") | .id')
FGA_FLAGS="--api-url http://localhost:9080 --api-token Azerty123_ --store-id $STORE_ID"
```

## Schema reference

Read the authorization schema at `fred-core/fred_core/security/rebac/schema.fga` to understand the types, relations, and permission rules before answering.

## Available commands

### 1. Read tuples

List stored relationship tuples, optionally filtered.

```bash
# All tuples
fga tuple read $FGA_FLAGS

# Filter by object
fga tuple read $FGA_FLAGS --object <type>:<id>

# Filter by object + relation
fga tuple read $FGA_FLAGS --object <type>:<id> --relation <relation>

# Filter by user
fga tuple read $FGA_FLAGS --user <type>:<id>
```

### 2. Check a permission

Check if a user has a specific relation on an object (returns `allowed: true/false`).

```bash
fga query check $FGA_FLAGS <user_type>:<user_id> <relation> <object_type>:<object_id>
```

### 3. List objects a user can access

List all objects of a given type that a user has a relation on.

```bash
fga query list-objects $FGA_FLAGS <user_type>:<user_id> <relation> <object_type>
```

### 4. List users who have access to an object

```bash
fga query list-users $FGA_FLAGS <object_type>:<object_id> <relation> <user_type>
```

### 5. Expand a relation (userset tree)

Show the full resolution tree for a relation on an object.

```bash
fga query expand $FGA_FLAGS <relation> <object_type>:<object_id>
```

## Handling `$ARGUMENTS`

Parse the user's intent from `$ARGUMENTS`. Examples:

- `/fga read tuples for tag:abc` → `fga tuple read $FGA_FLAGS --object tag:abc`
- `/fga can user:xyz read tag:abc?` → `fga query check $FGA_FLAGS user:xyz read tag:abc`
- `/fga why can user:xyz read tag:abc?` → Run `check`, then `expand`, then trace the tuple chain to explain the full resolution path
- `/fga list objects user:xyz can read of type tag` → `fga query list-objects $FGA_FLAGS user:xyz read tag`
- `/fga who can read tag:abc?` → `fga query list-users $FGA_FLAGS tag:abc read user`

## Explaining a permission ("why" queries)

When the user asks **why** a user has a permission, follow this process:

1. **Check** the permission exists: `fga query check ...`
2. **Expand** the relation on the object: `fga query expand ...`
3. **Read tuples** on the object to find the direct relationships: `fga tuple read ... --object <object>`
4. **Trace indirect paths**: if the relation comes through a team, parent, or other intermediary, read tuples on those intermediary objects too
5. **Read the schema** to explain which rule in the model grants the access
6. **Summarize** the full chain in a clear, human-readable format showing each hop

Example output format:
```
user:alice → member of → team:engineering → owner of → tag:docs → read (via "member from owner" rule)
```

## Notes

- Types in the schema: `user`, `organization`, `team`, `agent`, `tag`, `document`, `resource`
- Common relations: `owner`, `editor`, `viewer`, `member`, `manager`, `admin`, `parent`
- Common permissions: `read`, `update`, `delete`, `share`, `process`
