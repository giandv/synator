import base64

import kopf
import kubernetes
import os
import requests

WATCH_NAMESPACE = os.getenv('WATCH_NAMESPACE', "")
API_ENDPOINT = os.getenv("API_ENDPOINT", "")
API_KEY = os.getenv("API_KEY", "")
PROJECT_ID = os.getenv("PROJECT_ID", "")
all_namespaces = WATCH_NAMESPACE.split(',')

SYNATOR_WATCH = 'synator/watch'
SYNATOR_SYNC = 'synator/sync'
SYNATOR_RELOAD = 'synator/reload'
SYNATOR_REPLACE = 'synator/replace'
SYNATOR_REPLACE_IN = 'synator/replace-in'
SYNATOR_INCLUDE_NAMESPACE = 'synator/include-namespaces'
SYNATOR_EXCLUDE_NAMESPACES = 'synator/exclude-namespaces'


def watch_namespace(namespace, **_):
    if WATCH_NAMESPACE == "" or namespace in all_namespaces:
        return True
    return False


@kopf.on.create('', 'v1', 'secrets', annotations={SYNATOR_WATCH: 'yes'}, when=watch_namespace)
@kopf.on.update('', 'v1', 'secrets', annotations={SYNATOR_WATCH: 'yes'}, when=watch_namespace)
def update_secret_manager(body, meta, spec, status, old, new, diff, **kwargs):
    api = kubernetes.client.CoreV1Api()
    secret = api.read_namespaced_secret(meta.name, meta.namespace)
    if SYNATOR_REPLACE in secret.metadata.annotations and SYNATOR_REPLACE_IN in secret.metadata.annotations:
        name_secret_manager = secret.metadata.annotations[SYNATOR_REPLACE_IN]
        sec_key = secret.metadata.annotations[SYNATOR_REPLACE]
        sec_data = secret.data[sec_key]
        value = base64.b64decode(sec_data.strip().split()[1].translate(None, '}\''))
        my_headers = {'Api-Key': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}
        my_body = {'name': name_secret_manager, 'value': value, 'projectId': PROJECT_ID}
        try:
            response = requests.post(API_ENDPOINT + "/api/internal/secret/add-version", data=my_body,
                                     headers=my_headers)
            response.raise_for_status()
        except requests.exceptions.HTTPError as error:
            print(error)
    else:
        print('Error: There is no reference of the secret to be updated')


@kopf.on.create('', 'v1', 'secrets', annotations={SYNATOR_SYNC: 'yes'}, when=watch_namespace)
@kopf.on.update('', 'v1', 'secrets', annotations={SYNATOR_SYNC: 'yes'}, when=watch_namespace)
def update_secret(body, meta, spec, status, old, new, diff, **kwargs):
    api = kubernetes.client.CoreV1Api()
    namespace_response = api.list_namespace()
    namespaces = [nsa.metadata.name for nsa in namespace_response.items]
    namespaces.remove(meta.namespace)

    secret = api.read_namespaced_secret(meta.name, meta.namespace)
    secret.metadata.annotations.pop(SYNATOR_SYNC)
    secret.metadata.resource_version = None
    secret.metadata.uid = None
    for ns in parse_target_namespaces(meta, namespaces):
        secret.metadata.namespace = ns
        # try to pull the Secret object then patch it, try creating it if we can't
        try:
            api.read_namespaced_secret(meta.name, ns)
            api.patch_namespaced_secret(meta.name, ns, secret)
        except kubernetes.client.rest.ApiException as e:
            print(e.args)
            api.create_namespaced_secret(ns, secret)


@kopf.on.create('', 'v1', 'configmaps', annotations={SYNATOR_SYNC: 'yes'}, when=watch_namespace)
@kopf.on.update('', 'v1', 'configmaps', annotations={SYNATOR_SYNC: 'yes'}, when=watch_namespace)
def update_config_map(body, meta, spec, status, old, new, diff, **kwargs):
    api = kubernetes.client.CoreV1Api()
    namespace_response = api.list_namespace()
    namespaces = [nsa.metadata.name for nsa in namespace_response.items]
    namespaces.remove(meta.namespace)

    cfg = api.read_namespaced_config_map(meta.name, meta.namespace)
    cfg.metadata.annotations.pop(SYNATOR_SYNC)
    cfg.metadata.resource_version = None
    cfg.metadata.uid = None
    for ns in parse_target_namespaces(meta, namespaces):
        cfg.metadata.namespace = ns
        # try to pull the ConfigMap object then patch it, try to create it if we can't
        try:
            api.read_namespaced_config_map(meta.name, ns)
            api.patch_namespaced_config_map(meta.name, ns, cfg)
        except kubernetes.client.rest.ApiException as e:
            print(e.args)
            api.create_namespaced_config_map(ns, cfg)


def parse_target_namespaces(meta, namespaces):
    namespace_list = []
    # look for a namespace inclusion label first, if we don't find that, assume all namespaces are the target
    if SYNATOR_INCLUDE_NAMESPACE in meta.annotations:
        value = meta.annotations[SYNATOR_INCLUDE_NAMESPACE]
        namespaces_to_include = value.replace(' ', '').split(',')
        for ns in namespaces_to_include:
            if ns in namespaces:
                namespace_list.append(ns)
            else:
                print(
                    f"WARNING: include-namespaces requested I add this resource to a non-existing namespace: {ns}")
    else:
        # we didn't find a namespace inclusion label, so let's see if we were told to exclude any
        namespace_list = namespaces
        if SYNATOR_EXCLUDE_NAMESPACES in meta.annotations:
            value = meta.annotations[SYNATOR_EXCLUDE_NAMESPACES]
            namespaces_to_exclude = value.replace(' ', '').split(',')
            if len(namespaces_to_exclude) < 1:
                print(
                    "WARNING: exclude-namespaces was specified, but no values were parsed")

            for ns in namespaces_to_exclude:
                if ns in namespace_list:
                    namespace_list.remove(ns)
                else:
                    print(
                        f"WARNING: I was told to exclude namespace {ns}, but it doesn't exist on the cluster")

    return namespace_list


@kopf.on.create('', 'v1', 'namespaces')
def new_namespace(spec, name, meta, logger, **kwargs):
    api = kubernetes.client.CoreV1Api()

    try:
        api_response = api.list_secret_for_all_namespaces()
        # TODO: Add configmap
        for secret in api_response.items:
            # Check secret have annotation
            if secret.metadata.annotations and secret.metadata.annotations.get(SYNATOR_SYNC) == "yes":
                secret.metadata.annotations.pop(SYNATOR_SYNC)
                secret.metadata.resource_version = None
                secret.metadata.uid = None
                for ns in parse_target_namespaces(secret.metadata, [name]):
                    secret.metadata.namespace = ns
                    try:
                        api.read_namespaced_secret(
                            secret.metadata.name, ns)
                        api.patch_namespaced_secret(
                            secret.metadata.name, ns, secret)
                    except kubernetes.client.rest.ApiException as e:
                        print(e.args)
                        api.create_namespaced_secret(ns, secret)
    except kubernetes.client.rest.ApiException as e:
        print("Exception when calling CoreV1Api->list_secret_for_all_namespaces: %s\n" % e)


# Reload Pod when update configmap or secret

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
