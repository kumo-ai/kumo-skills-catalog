---
name: k8s-egress-diagnose
description: This skill should be used when the user reports pod connectivity issues, timeout errors reaching external endpoints, "connection timed out", "max retries exceeded", or network problems from within Kubernetes pods.
allowed-tools: [Bash, Read, Grep, Glob]
---

# Kubernetes Pod Egress Connectivity Diagnosis

When a pod cannot reach an external endpoint, the cause is often an egress
network policy blocking outbound traffic.

## Diagnostic Steps

### 1. Test DNS and TCP from inside the pod

Use python3 since nslookup/dig may not be installed:

    kubectl exec -n <ns> <pod> -- python3 -c \
      "import socket; print(socket.getaddrinfo('<fqdn>', <port>))"

Then test TCP to the resolved IP, and also test a known-working endpoint
for comparison. If some endpoints work and others don't, it's egress
policy filtering.

### 2. Check egress network policies

    kubectl get ciliumnetworkpolicy -n <namespace> -o yaml
    kubectl get networkpolicy -n <namespace> -o yaml

Check whether the target FQDN is in the `toFQDNs` allow list. Note that
`matchName` is exact — the original FQDN must appear, not its CNAME.

### 3. Check the GitOps source of truth

Egress policies are typically managed via a dedicated git repo synced by
a GitOps controller. Ask the user which repo manages egress policies.
Compare live policies against git to detect config drift — manually-applied
policies may be pruned on next reconciliation.

### 4. Understand why the FQDN is being accessed

Before whitelisting, check pod logs and stack traces to understand the
call. Common cause: SDK upgrades switching from API-proxied access to
presigned URLs that go directly to backing cloud storage. The API endpoint
may be allowed but the storage endpoint is not.

## Gotchas

- **Image pulls work but pod egress doesn't**: Image pulls happen at node
  level (kubelet), not from within the pod network.
- **Some cloud endpoints work, others don't**: Identity endpoints (AAD,
  ARM) are often pre-whitelisted. This doesn't mean other endpoints are.
- **Presigned URL pattern**: First hop (API) allowed, second hop (cloud
  storage) blocked. Error shows as timeout to storage, not the API.
