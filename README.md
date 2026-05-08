# module-freezer

A Kubernetes DaemonSet that snapshots the currently loaded kernel modules on each node at startup and monitors for any new modules loaded afterward. If an unapproved module is detected, it logs a warning, creates a Kubernetes Event on the Node, and taints the node with `NoSchedule` to prevent new workloads from being scheduled.

Optionally, it can hard-lock module loading via `/proc/sys/kernel/modules_disabled` so that no new modules can be loaded until the node is rebooted.

## How It Works

1. On startup, reads `/proc/modules` and saves the set of loaded modules as the approved list
2. Polls every `POLL_INTERVAL` seconds (default: 30) for newly loaded modules
3. If an unapproved module is detected:
   - Logs a warning with the module name(s)
   - Creates a `Warning` event on the Node object with reason `UnapprovedModuleLoaded`
   - Taints the node with `module-freezer/unapproved-module=true:NoSchedule`

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|---|---|---|
| `NODE_NAME` | *(required)* | Node name, injected via downward API |
| `POLL_INTERVAL` | `30` | Seconds between module checks |
| `LOCK_MODULES` | `false` | Write `1` to `/proc/sys/kernel/modules_disabled` after snapshot (irreversible until reboot) |
| `REMOVE_TAINT_ON_RESOLVE` | `false` | Remove the taint if the unapproved module is later unloaded |

## Deployment

### Generic Kubernetes

```bash
make build push
make deploy
```

### OpenShift

```bash
make build push
make deploy-openshift
```

### Cleanup

```bash
make undeploy          # generic Kubernetes
make undeploy-openshift # OpenShift
```

## Building

```bash
# Build the container image
make build

# Build and push
make push

# Override image name/tag
make build IMAGE=my-registry.example.com/module-freezer TAG=v1.0.0
```

## RBAC

The agent requires a ClusterRole with:
- `nodes`: `get`, `patch` (for reading node state and applying taints)
- `events`: `create` (for creating warning events)

## Security Notes

- The container mounts `/proc` from the host as read-only
- Runs as non-root (UBI9 default UID 1001)
- `LOCK_MODULES=true` is a **one-way lock** — once set, no kernel modules can be loaded until the node is rebooted. Use with caution.
