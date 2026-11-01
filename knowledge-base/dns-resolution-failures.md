# DNS resolution failures in Kubernetes

## Symptoms
Applications log errors like:
- `Temporary failure in name resolution`
- `could not translate host name "..." to address`
- `dial tcp: lookup <name> on 10.96.0.10:53: no such host`
- `i/o timeout` while looking up a name

Calls to other services fail, or are about 5 seconds slower than usual (a DNS timeout followed by a retry).

## Likely causes
- CoreDNS pods are down, crash-looping or overloaded.
- A NetworkPolicy blocks egress to DNS on port 53 (UDP and TCP). This is common in namespaces with default deny (see "Kubernetes NetworkPolicy blocking traffic").
- The app uses the wrong service name or namespace.
- The upstream DNS server used for external names is failing.
- The default `ndots:5` setting makes every external lookup try several cluster suffixes first, which multiplies DNS traffic.

If the name resolves but connections fail, it's not a DNS problem. Check that the service has ready endpoints.

## How to diagnose
Check CoreDNS:

```bash
kubectl get pods -n kube-system -l k8s-app=kube-dns
kubectl logs -n kube-system -l k8s-app=kube-dns --tail 50
kubectl top pods -n kube-system -l k8s-app=kube-dns
```

Test from inside the namespace with a temporary pod:

```bash
kubectl run dnstest -n <namespace> --rm -it --restart=Never --image=busybox:1.36 -- sh
```

Then, inside the pod:

```bash
nslookup orders-api                              # same namespace
nslookup orders-api.prod.svc.cluster.local       # full name
nslookup example.com                             # external name
cat /etc/resolv.conf
```

If even this test pod can't resolve anything, check the namespace's NetworkPolicies.

Internal names follow the pattern `<service>.<namespace>.svc.cluster.local`. To call a service in another namespace you need at least `<service>.<namespace>`.

## Fix
- **CoreDNS down or overloaded:** restart it with `kubectl rollout restart deployment/coredns -n kube-system`, and add replicas if CPU is high. CoreDNS belongs to the Platform team, so tell them.
- **NetworkPolicy blocks DNS:** add an egress rule that allows UDP and TCP port 53 to pods labelled `k8s-app: kube-dns` in the `kube-system` namespace.
- **Wrong name:** fix the host name in the Helm values, and use the full name for services in other namespaces.
- **Too many external lookups:** use a fully qualified name with a trailing dot (for example `api.payments-provider.example.`), or set `ndots` to 2 in the pod's `dnsConfig.options`.
- **Upstream failure:** check the `forward` setting in the CoreDNS config and the status of the cloud DNS service.

## Escalate if
- DNS fails in every namespace. It's cluster-wide, so page the Platform team; SEV1 or SEV2 depending on the impact.
- Public DNS records for `example.com` are wrong. The Platform team manages them.
