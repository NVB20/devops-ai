# High CPU or memory usage

## Symptoms
- Alert "CPU usage above 90% for 10 minutes" or "Memory usage above 90%" fires.
- Requests get slow, time out, or return 504 errors.
- Pods restart with `OOMKilled`, or the Linux OOM killer kills a process.
- Kubernetes nodes show `MemoryPressure` and start evicting pods.
- CPU-limited containers are throttled: high latency even though average CPU looks normal.

## Likely causes
- A traffic spike (marketing campaign, retry storm from a client, bot traffic).
- A new release with a bug: an infinite loop, a slow query, or a memory leak.
- A batch job or cron job running at peak time.
- Resource limits set too low for the real load.
- Garbage collection pressure in the application runtime.
- A noisy neighbour: another pod on the same node using most of the resources.
- An unknown process using CPU (possible crypto miner on a compromised host).

## How to diagnose
On a Linux host:

```bash
uptime                                  # load average; compare with the number of CPU cores (nproc)
top -o %CPU                             # or htop
ps aux --sort=-%mem | head -15
free -m
vmstat 1 5                              # high "wa" column means waiting on disk, not CPU
dmesg -T | grep -i -E "killed process|out of memory"
```

On Kubernetes:

```bash
kubectl top nodes
kubectl top pods -n <namespace> --sort-by=cpu
kubectl top pods -n <namespace> --sort-by=memory
kubectl describe node <node-name>       # "Allocated resources" and "Conditions"
kubectl get hpa -n <namespace>
```

Then answer three questions using the Grafana dashboard for the service:
1. Did traffic go up? Compare requests per second with the same time last week.
2. Did a deploy happen just before the usage went up?
3. Is it one pod, all pods of one service, or the whole node?

Memory that grows steadily over hours or days and drops after each restart is a memory leak.

## Fix
- **Traffic spike:** scale out: `kubectl scale deployment/<name> -n <namespace> --replicas=<n>`, or raise `maxReplicas` on the HPA. Check that the database can handle the extra connections (see "Database connection errors").
- **Bad release:** roll back (see "Deploy and rollback procedure").
- **Memory leak:** restarting the pods buys time (`kubectl rollout restart deployment/<name>`). If possible, take a heap dump before the restart and open a bug for the owning team.
- **CPU throttling:** raise the CPU limit, or remove the CPU limit and keep only the CPU request.
- **Batch job at peak:** pause or reschedule it to a quiet time.
- **One process on a VM:** only kill a process when you know what it is and what it does.

## Escalate if
- A node is unresponsive, or several nodes are under pressure at once. Page the Platform team.
- Scaling out doesn't reduce the load.
- You find a process you don't recognise using high CPU. Treat it as a possible compromise: don't kill it, and contact the Security team immediately (see "Suspected compromised host or container").
- Customers are affected for more than 15 minutes. Declare an incident (see "Incident and escalation process").
