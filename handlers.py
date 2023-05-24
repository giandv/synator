import kopf
import kubernetes
import os
import sys

EXCLUDE_NAMESPACE   = os.getenv('EXCLUDE_NAMESPACE', "")
all_namespaces      = EXCLUDE_NAMESPACE.split(',')
SYNATOR_RELOAD      = 'synator/reload'

def watch_namespace(namespace, **_):
    if namespace in all_namespaces:
        return False
    return True

# Reload Pod when update configmap
@kopf.on.update('', 'v1', 'configmaps', when=watch_namespace)
def reload_pod_config(body, meta, spec, status, old, new, diff, **kwargs):
    try:
        # Get namespace
        ns = meta.namespace
        api = kubernetes.client.CoreV1Api()
        pods = api.list_namespaced_pod(ns)
        print(ns, meta.name)
        for pod in pods.items:
            print("Pod name: " + pod.metadata.name)
            # Find which pods use this secrets
            if pod.metadata.annotations and pod.metadata.annotations.get(SYNATOR_RELOAD):
                print("Configmaps reloader:")
                print(pod.metadata.annotations.get(SYNATOR_RELOAD).split(','))
                print("Configmap name: " + meta.name)
                reload_configuration = pod.metadata.annotations.get(SYNATOR_RELOAD).split(',')
                find_configmap = "configmap:" + meta.name
                if meta.name in reload_configuration or find_configmap in reload_configuration:
                    print("Reload pod: " + pod.metadata.name)
                    api.delete_namespaced_pod(pod.metadata.name, pod.metadata.namespace)
    except:
        sys.exit(0)

# Reload Pod when update secret
@kopf.on.update('', 'v1', 'secrets', when=watch_namespace)
def reload_pod_secret(body, meta, spec, status, old, new, diff, **kwargs):
    try:
        # Get namespace
        ns = meta.namespace
        api = kubernetes.client.CoreV1Api()
        pods = api.list_namespaced_pod(ns)
        print(ns, meta.name)
        for pod in pods.items:
            print("Pod name: " + pod.metadata.name)
            # Find which pods use this secrets
            if pod.metadata.annotations and pod.metadata.annotations.get(SYNATOR_RELOAD):
                print("Secrets reloader:")
                print(pod.metadata.annotations.get(SYNATOR_RELOAD).split(','))
                print("Secret name: " + meta.name)
                reload_configuration = pod.metadata.annotations.get(SYNATOR_RELOAD).split(',')
                find_secret = "secret:" + meta.name
                if meta.name in reload_configuration or find_secret in reload_configuration:
                    print("Reload pod: " + pod.metadata.name)
                    api.delete_namespaced_pod(pod.metadata.name, pod.metadata.namespace)
    except:
        sys.exit(0)