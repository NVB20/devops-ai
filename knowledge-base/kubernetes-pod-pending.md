# Kubernetes pod stuck in Pending

## Symptoms
- `kubectl get pods` shows the pod as `Pending` for more than a minute or two.
- The deployment has fewer ready replicas than it should. The HPA scaled up, but the new pods don't start.
- Events show `FailedScheduling`.

## Likely causes
- No node has enough free CPU or memory for the pod's resource **requests**.
- A `nodeSelector` or node affinity rule matches no node.
- The nodes have taints that the pod doesn't tolerate.
- The PersistentVolumeClaim is not bound (wrong storage class, or the volume is in another zone).
- Pod anti-affinity can't be satisfied (for example "one replica per node" with more replicas than nodes).
- The cluster autoscaler can't add nodes: it reached its maximum size or the cloud quota.

If the namespace ResourceQuota is exceeded, the pod isn't created at all. You'll see `FailedCreate` on the ReplicaSet instead of a Pending pod.

## How to diagnose
```bash
kubectl describe pod <pod-name> -n <namespace>
```

Read the `FailedScheduling` event. It says why each node was rejected, for example:

```
0/6 nodes are available: 3 Insufficient memory, 2 node(s) had untolerated taint {dedicated: data},
1 node(s) didn't match Pod's node affinity/selector.
```

Then check capacity, storage and quota:

```bash
kubectl describe nodes | grep -A 8 "Allocated resources"
kubectl top nodes
kubectl get pvc -n <namespace>
kubectl describe pvc <pvc-name> -n <namespace>
kubectl get resourcequota -n <namespace>
kubectl describe replicaset -n <namespace> -l app=<name>
kubectl logs -n kube-system deploy/cluster-autoscaler --tail 50
```

The scheduler uses **requests**, not real usage. A node can look idle in `kubectl top` and still be "full" for the scheduler.

## Fix
- **Insufficient CPU or memory:** if the requests are much higher than real usage (check the Grafana dashboard), lower them. Otherwise scale down something you don't need, or let the autoscaler add a node. If the autoscaler is at its maximum, ask the Platform team.
- **Selector or affinity:** fix the labels in the Helm values, or label the node if that was the plan.
- **Taints:** only add a toleration if the pod really belongs on those nodes. Nodes with the taint `dedicated: data` are reserved for the Data team.
- **PVC not bound:** check the storage class name, and that the volume is in the same zone as a node with free capacity.
- **Anti-affinity:** change `requiredDuringSchedulingIgnoredDuringExecution` to `preferredDuringSchedulingIgnoredDuringExecution`, or reduce the number of replicas.
- **Quota:** remove unused workloads in the namespace, or open a ticket to the Platform team for a bigger quota.

## Escalate if
- Many pods across namespaces are Pending. The cluster is out of capacity, so contact the Platform team.
- A prod service can't scale out during a traffic spike (see "High CPU or memory usage"). Declare an incident if customers are affected.
