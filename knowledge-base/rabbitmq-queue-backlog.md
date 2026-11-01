# RabbitMQ queue backlog growing

## Symptoms
- Order confirmation emails arrive late, or not at all.
- The alert "RabbitMQ queue depth above 1000 for 10 minutes" fires for the `notifications.order-created` queue.
- The RabbitMQ management UI shows the number of `Ready` messages growing, with few or zero consumers.
- In bad cases orders-api logs `connection blocked` and creating orders gets slow.

## Likely causes
- notifications-worker is down, crash-looping, or scaled to zero.
- The worker is slow because the email provider is slow or rate-limits us.
- A "poison" message fails every time and is put back in the queue forever, keeping the worker busy.
- The prefetch setting is wrong, so one worker holds many messages it can't process.
- RabbitMQ raised a memory or disk alarm and is blocking publishers.

## How to diagnose
Check the consumer:

```bash
kubectl get pods -n prod -l app=notifications-worker
kubectl logs -n prod -l app=notifications-worker --tail 100
```

Check the queues and alarms on a RabbitMQ node (or with `kubectl exec` into a RabbitMQ pod), or in the management UI:

```bash
rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers
rabbitmq-diagnostics alarms
```

How to read the output:
- `consumers` is 0: the worker isn't connected.
- `messages_unacknowledged` is high and not moving: the worker took messages but isn't finishing them.
- The same message ID fails again and again in the worker logs: a poison message.
- An alarm is listed: publishers are blocked. This affects orders, not only emails.

## Fix
- **Worker down:** fix the crash (see "Kubernetes pod stuck in CrashLoopBackOff") or scale it back up.
- **Worker slow:** add replicas with `kubectl scale deployment/notifications-worker -n prod --replicas=<n>`. Check the email provider's status page first; if they are rate-limiting us, more replicas won't help.
- **Poison message:** the queue has a dead-letter exchange. After 3 failed attempts the worker should reject the message without requeue, so it moves to `notifications.dead-letter`. If that isn't happening, use "Get messages" in the management UI with ack mode "Reject requeue false" to move the message to the dead-letter queue, and give the message ID to the Orders team. Messages contain customer email addresses, so don't paste them into chat.
- **Memory or disk alarm:** page the Data team. The alarm clears once memory or disk is freed on RabbitMQ.

Never purge the queue to make the alert go away. Every message is a customer email.

## Escalate if
- An alarm is blocking publishers, so orders are affected. This is a SEV2: page the Data team.
- The oldest message is more than 1 hour old. This is a SEV3: tell the Orders team (see "Incident and escalation process").
