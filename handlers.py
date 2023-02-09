import kopf
import kubernetes
import os

EXCLUDE_NAMESPACE   = os.getenv('EXCLUDE_NAMESPACE', "")
all_namespaces      = EXCLUDE_NAMESPACE.split(',')
SYNATOR_RELOAD      = 'synator/reload'


def watch_namespace(namespace, **_):
    if EXCLUDE_NAMESPACE == "":
        return True
    if namespace in all_namespaces:
        return False
    return True

# Reload Pod when update configmap
@kopf.on.update('', 'v1', 'configmaps', when=watch_namespace)
def reload_pod_config(body, meta, spec, status, old, new, diff, **kwargs):
    # Get namespace
    ns = meta.namespace
    api = kubernetes.client.CoreV1Api()
    pods = api.list_namespaced_pod(ns)
    print(ns, meta.name)
    for pod in pods.items:
        # Find which pods use this secrets
        if pod.metadata.annotations and pod.metadata.annotations.get(SYNATOR_RELOAD):
            if any('configmap:' + meta.name in s for s in pod.metadata.annotations.get(SYNATOR_RELOAD).split(',')):
                # Reload pod
                api.delete_namespaced_pod(
                    pod.metadata.name, pod.metadata.namespace)

# Reload Pod when update secret
@kopf.on.update('', 'v1', 'secrets', when=watch_namespace)
def reload_pod_secret(body, meta, spec, status, old, new, diff, **kwargs):
    # Get namespace
    ns = meta.namespace
    api = kubernetes.client.CoreV1Api()
    pods = api.list_namespaced_pod(ns)
    print(ns, meta.name)
    for pod in pods.items:
        # Find which pods use this secrets
        if pod.metadata.annotations and pod.metadata.annotations.get(SYNATOR_RELOAD):
            if any('secret:' + meta.name in s for s in pod.metadata.annotations.get(SYNATOR_RELOAD).split(',')):
                # Reload pod
                api.delete_namespaced_pod(
                    pod.metadata.name, pod.metadata.namespace)
