# Suspected compromised host or container

## Signs
- A process you don't recognise is using a lot of CPU. Crypto miners are the most common case.
- Outbound connections from a server or pod to unknown IP addresses or unusual ports.
- New user accounts, SSH keys, cron jobs or systemd services that nobody created.
- Pods, DaemonSets or RoleBindings in the cluster that no team owns.
- Executable files in `/tmp` or `/dev/shm`.
- Audit log entries from an identity at an unusual time or location.
- A sudden jump in the cloud bill or in outbound traffic.

## First rules
1. **Contact the Security team immediately** by paging them, and declare a SEV1 in a private incident channel.
2. **Don't power off, delete or rebuild anything yet.** Memory, running processes and disk contents are evidence.
3. **Don't kill the suspicious process** unless it's causing damage right now and the Security team agrees. Killing it can trigger clean-up code that destroys evidence.
4. **Write everything down** with the time: what you saw, every command you ran, and every change you made.
5. **Don't type passwords or other secrets on that host.**

## Contain
Isolate it so it can't spread or send data out, but keep it running.

**Kubernetes pod:**

```bash
kubectl label pod <pod-name> -n <namespace> app=quarantined --overwrite
kubectl cordon <node-name>
```

Changing the `app` label does two things. The Deployment no longer counts the pod, so it starts a healthy replacement. And the `prod` allow policies no longer match the pod, so default deny blocks its traffic. NetworkPolicies only ever add permissions, so also check `kubectl get networkpolicy -n <namespace>` for policies that match all pods (an empty `podSelector`), such as the DNS rule, and tell the Security team about them.

**VM or node:**
- Ask the Platform team to change the firewall rules so all traffic is blocked except from the Security team's investigation host.
- Take a disk snapshot in the cloud console.

## Collect (read-only)
If the Security team asks you to collect information before they arrive:

```bash
date; hostname; uptime
ps auxf
ss -tunap
last -n 20
getent passwd | awk -F: '$3 >= 1000'
crontab -l; ls -la /etc/cron.* /var/spool/cron 2>/dev/null
ls -la /tmp /dev/shm
systemctl list-units --type=service --state=running
```

For a pod:

```bash
kubectl get pod <pod-name> -n <namespace> -o yaml > pod.yaml
kubectl logs <pod-name> -n <namespace> > pod.log
```

Save everything to the incident's secure storage, not to chat.

## Recover
- Never "clean" a compromised host and keep using it. Rebuild it from a known-good image, and redeploy containers from images in `registry.example.com` that passed the pipeline.
- Rotate every secret the host or pod could read, including service account tokens (see "Secret rotation procedure").
- Find out how the attacker got in (a vulnerable dependency, an exposed port, a leaked credential) and fix it before going back to normal.
- The Security team leads a postmortem within 5 business days.

## Escalate if
Always. This is a Security team incident from the first minute. Also page the Platform team to help with isolation, and the engineering manager on duty (see "Incident and escalation process").
