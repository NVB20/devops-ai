# Kubernetes node NotReady

## Symptoms
- `kubectl get nodes` shows one or more nodes as `NotReady`.
- The alert "KubeNodeNotReady" fires.
- Pods on that node show `Unknown` or `Terminating`. After about 5 minutes, Kubernetes starts creating replacement pods on other nodes.
- The node conditions show `DiskPressure`, `MemoryPressure` or `PIDPressure`.

## Likely causes
- The kubelet stopped or crashed.
- The container runtime (containerd) is unhealthy.
- The node's disk is full of images and logs, causing DiskPressure.
- The node ran out of memory and the kernel killed system processes.
- Network problems: the node can't reach the API server, or the CNI (network plugin) pod on that node failed.
- The kubelet's client certificate expired.
- The cloud provider stopped, rebooted or is replacing the VM.

## How to diagnose
```bash
kubectl get nodes -o wide
kubectl describe node <node-name>          # Conditions, Events, last heartbeat
kubectl get pods -A -o wide --field-selector spec.nodeName=<node-name>
kubectl get pods -n kube-system -o wide | grep <node-name>
```

If you have SSH access to the node (Platform team):

```bash
systemctl status kubelet containerd
journalctl -u kubelet --since "30 min ago" | tail -50
df -h /var/lib/containerd /var/log
free -m
```

In the cloud console, check that the VM is running and whether there was a maintenance event.

## Fix
First stop new pods from being scheduled on the node:

```bash
kubectl cordon <node-name>
```

Then:
- **kubelet or containerd stopped:** `sudo systemctl restart containerd kubelet`, then watch `kubectl get nodes -w`.
- **Disk pressure:** remove unused images with `sudo crictl rmi --prune`, and see "Disk full on a server".
- **Memory pressure:** find which pods use the most memory and check their limits (see "High CPU or memory usage").
- **Can't fix it quickly:** drain the node and replace it. Nodes are replaceable; don't spend an hour repairing one:
  ```bash
  kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
  ```
  Then delete the VM and the node group creates a new one.
- When the node is healthy again: `kubectl uncordon <node-name>`.

Draining respects PodDisruptionBudgets. If a drain hangs, check `kubectl get pdb -A` to see which budget is blocking it. Don't force the drain in `prod` without checking what will go down.

## Escalate if
- More than one node is NotReady at the same time. That points to a cluster, network or cloud problem: page the Platform team and declare a SEV2.
- The API server itself is unreachable.
- You find processes on the node you don't recognise (see "Suspected compromised host or container").
