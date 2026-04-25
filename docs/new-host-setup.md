# New Host Setup

How to authorize a fresh machine as a Hopper client for an existing namespace.
Assumes the upstream server is already running (e.g. `hopper.api.app` under
systemd-user on ember) and you have admin access to it.

## Roles in this flow

- **Admin host** — holds `admin.key`, grants DID roles. For this deployment: `ember`.
- **Approver** — a DID granted `approver` on a namespace; can invite/approve others
  for that namespace without needing `admin.key`. Granted once per workstation
  per namespace you actively manage.
- **New host** — the machine being added as a client.

## Identity rule

One DID per host. Never copy a DID from another host's `upstream status`, memory,
or a note. Always confirm with `hopper upstream whoami` on the host in question
before granting or redeeming.

## Bootstrap sequence

### 1. On the new host — install and generate identity

```bash
git clone https://github.com/apathy-ca/hopper.git ~/hopper
cd ~/hopper && pip install -e .

hopper upstream set-server https://hopper.henrynet.ca
hopper upstream init
hopper upstream whoami
# → did:key:z6Mk...  ← copy this exact string
```

### 2. On an approver host (or admin) — issue an invite

If you already have `approver` on the target namespace:

```bash
hopper upstream invite create -n <NAMESPACE> -e 1h
# → hinv_...
```

If you get `not authorized to invite for namespace '<NAMESPACE>'`, you need the
approver role first — see step 2a.

#### 2a. Granting approver (admin host only, one-time per workstation)

On the admin host (ember), with `admin.key`:

```bash
hopper upstream admin approve <DID_FROM_WHOAMI> \
  -n <NAMESPACE> -r approver -k ./admin.key
```

After this, that workstation can issue invites for `<NAMESPACE>` without the
admin key.

### 3. On the new host — redeem

```bash
hopper upstream redeem <TOKEN>
# → ✓ redeemed: approved on '<NAMESPACE>'
```

### 4. Initialize the project instance

```bash
cd ~/path/to/<project>
hopper init --name <NAMESPACE> --auto-detect
```

### 5. Verify instance.id before first sync

Open `.hopper/config.yaml` and confirm `instance.id` matches `<NAMESPACE>`
**verbatim** (case-sensitive). Mismatched ids silently shard — sync reports
healthy but pulls zero tasks.

```bash
grep -E "^  (id|name):" .hopper/config.yaml
```

### 6. First sync

```bash
hopper upstream status      # sanity: server, DID, enabled
hopper upstream sync -v     # should show pushed/pulled counts
hopper task list
```

If `sync -v` says "already up to date" and `task list` is empty, you have the
sharding bug — re-check step 5.

## Host → DID → role ledger

Keep this current. Update when a host is added, reimaged, or revoked.

| Host          | Role            | Namespace(s)       | DID                                        |
|---------------|-----------------|--------------------|--------------------------------------------|
| ember         | admin           | *                  | _fill in_                                  |
| _workstation_ | approver        | Rosetta_Program    | _fill in_                                  |
| _gpu-runner_  | approved        | Rosetta_Program    | _fill in_                                  |

## Troubleshooting

- **`not authorized to invite for namespace 'X'`** — the signing DID lacks
  `approver` on X. Check `whoami` on the host running the invite; grant approver
  from the admin host (step 2a).
- **`DID authentication failed`** — the command is using a key the server doesn't
  recognize (wrong key file, wrong server URL, or host was never registered).
- **Sync succeeds but pulls nothing** — `instance.id` mismatch. See step 5.
- **Admin key on the wrong box** — `admin.key` lives only on the admin host
  (ember). Don't copy it. Grant approver to your workstation DID instead and do
  day-to-day invites from there.

## Server ops reminders

- `~/.hopper/upstream-data/` on ember is production state. Snapshot before any
  schema or instance-id migration.
- Only one server process per storage path. The systemd-user unit owns uvicorn;
  don't run `hopper upstream server` ad-hoc on ember.
