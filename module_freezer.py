#!/usr/bin/env python3
import datetime
import logging
import os
import signal
import sys
import time

from kubernetes import client, config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("module-freezer")

PROC_MODULES = os.environ.get("PROC_MODULES_PATH", "/host/proc/modules")
PROC_MODULES_DISABLED = os.environ.get(
    "PROC_MODULES_DISABLED_PATH", "/host/proc/sys/kernel/modules_disabled"
)
NODE_NAME = os.environ.get("NODE_NAME")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))
LOCK_MODULES = os.environ.get("LOCK_MODULES", "false").lower() == "true"
REMOVE_TAINT_ON_RESOLVE = (
    os.environ.get("REMOVE_TAINT_ON_RESOLVE", "false").lower() == "true"
)

TAINT_KEY = "module-freezer/unapproved-module"
TAINT_VALUE = "true"
TAINT_EFFECT = "NoSchedule"

shutdown = False


def handle_signal(signum, frame):
    global shutdown
    log.info("Received signal %d, shutting down", signum)
    shutdown = True


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


def read_loaded_modules():
    with open(PROC_MODULES) as f:
        return {line.split()[0] for line in f if line.strip()}


def lock_modules():
    log.warning("LOCK_MODULES enabled — writing 1 to %s", PROC_MODULES_DISABLED)
    log.warning("This is irreversible until reboot. No new modules can be loaded.")
    with open(PROC_MODULES_DISABLED, "w") as f:
        f.write("1")
    log.info("Kernel module loading is now disabled")


def taint_node(v1):
    node = v1.read_node(NODE_NAME)
    taints = node.spec.taints or []

    for t in taints:
        if t.key == TAINT_KEY:
            return

    taints.append(
        client.V1Taint(key=TAINT_KEY, value=TAINT_VALUE, effect=TAINT_EFFECT)
    )
    node.spec.taints = taints
    v1.patch_node(NODE_NAME, node)
    log.info("Tainted node %s with %s=%s:%s", NODE_NAME, TAINT_KEY, TAINT_VALUE, TAINT_EFFECT)


def remove_taint(v1):
    node = v1.read_node(NODE_NAME)
    taints = node.spec.taints or []
    new_taints = [t for t in taints if t.key != TAINT_KEY]

    if len(new_taints) == len(taints):
        return

    node.spec.taints = new_taints if new_taints else None
    v1.patch_node(NODE_NAME, node)
    log.info("Removed taint %s from node %s", TAINT_KEY, NODE_NAME)


def create_event(v1, modules):
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    module_list = ", ".join(sorted(modules))
    event = client.CoreV1Event(
        metadata=client.V1ObjectMeta(
            generate_name="module-freezer-",
            namespace="default",
        ),
        involved_object=client.V1ObjectReference(
            kind="Node",
            name=NODE_NAME,
            api_version="v1",
        ),
        reason="UnapprovedModuleLoaded",
        message=f"Unapproved kernel module(s) detected: {module_list}",
        type="Warning",
        source=client.V1EventSource(component="module-freezer"),
        first_timestamp=now,
        last_timestamp=now,
    )
    v1.create_namespaced_event("default", event)
    log.info("Created Kubernetes event for unapproved modules: %s", module_list)


def main():
    if not NODE_NAME:
        log.error("NODE_NAME environment variable is required")
        sys.exit(1)

    try:
        config.load_incluster_config()
    except config.ConfigException:
        log.warning("Not running in-cluster, falling back to kubeconfig")
        config.load_kube_config()

    v1 = client.CoreV1Api()

    approved = read_loaded_modules()
    log.info(
        "Snapshot complete: %d modules approved on node %s", len(approved), NODE_NAME
    )
    for mod in sorted(approved):
        log.debug("  approved: %s", mod)

    if LOCK_MODULES:
        lock_modules()

    node_is_tainted = False

    while not shutdown:
        time.sleep(POLL_INTERVAL)
        if shutdown:
            break

        current = read_loaded_modules()
        new_modules = current - approved

        if new_modules:
            log.warning(
                "Unapproved module(s) detected on %s: %s",
                NODE_NAME,
                ", ".join(sorted(new_modules)),
            )
            try:
                create_event(v1, new_modules)
            except Exception:
                log.exception("Failed to create Kubernetes event")
            try:
                taint_node(v1)
                node_is_tainted = True
            except Exception:
                log.exception("Failed to taint node %s", NODE_NAME)
        elif node_is_tainted and REMOVE_TAINT_ON_RESOLVE:
            log.info("All modules now approved, removing taint from %s", NODE_NAME)
            try:
                remove_taint(v1)
                node_is_tainted = False
            except Exception:
                log.exception("Failed to remove taint from node %s", NODE_NAME)
        else:
            log.debug("Check passed: no unapproved modules on %s", NODE_NAME)

    log.info("Shutting down module-freezer")


if __name__ == "__main__":
    main()
