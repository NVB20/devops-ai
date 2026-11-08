# Kafka consumer lag growing

## Symptoms
- The alert "Kafka consumer lag above 10000 for 15 minutes" fires for the `analytics-consumer` group.
- The sales dashboards in Grafana show yesterday's numbers, or numbers that stop at a certain time.
- `kafka-consumer-groups` shows the `LAG` column growing on the `orders.events` topic.
- Customers see nothing: orders, payments and emails don't go through Kafka. Only analytics is late.

## How we monitor it
Lag is the number of messages written to a partition that the consumer group hasn't read yet. It is measured per partition, from the latest offset minus the group's committed offset.
- **kafka-exporter** exposes `kafka_consumergroup_lag` to Prometheus, per topic, partition and group.
- The Grafana dashboard "Kafka" has a panel "Consumer lag by group". Watch the trend, not one value: lag that rises and falls with traffic is normal, lag that only grows means the consumer is falling behind.
- The alert uses the sum over all partitions: `sum by (consumergroup) (kafka_consumergroup_lag{consumergroup="analytics-consumer"}) > 10000` for 15 minutes.

## Likely causes
- analytics-consumer is down, crash-looping, or scaled to zero.
- A traffic peak (a sale, a marketing email) writes faster than the consumer reads.
- The consumer is slow because its database writes are slow.
- A message it can't parse makes it crash on the same offset again and again.
- Consumers keep rebalancing (pods restarting, or processing takes longer than `max.poll.interval.ms`), so nobody reads for long periods.
- One partition gets most of the messages (a hot key), so one consumer is behind while the others are idle.

## How to diagnose
Check the consumer pods:

```bash
kubectl get pods -n prod -l app=analytics-consumer
kubectl logs -n prod -l app=analytics-consumer --tail 100
```

Check the group's lag per partition (from a Kafka broker pod):

```bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group analytics-consumer
```

How to read the output:
- `CONSUMER-ID` is empty for all partitions: no consumer is connected.
- `CURRENT-OFFSET` doesn't move between two runs a minute apart: the consumer is stuck, often on one bad message (same offset in the logs every time).
- Lag on one partition only: a hot key or one stuck consumer.
- Logs show "rebalancing" or "member left the group" often: a rebalance loop.

## Fix
- **Consumer down:** fix the crash (see "Kubernetes pod stuck in CrashLoopBackOff") or scale it back up.
- **Traffic peak:** add replicas with `kubectl scale deployment/analytics-consumer -n prod --replicas=<n>`. More replicas than partitions don't help: `orders.events` has 6 partitions, so 6 is the maximum.
- **Bad message:** the consumer sends messages that fail 3 times to `orders.events.dead-letter`. If it doesn't, ask the Data team to skip that one offset with `kafka-consumer-groups.sh --reset-offsets --to-offset <offset+1> --topic orders.events:<partition>` while the group is stopped. Note the offset first: the message is lost for analytics.
- **Rebalance loop:** check for restarts (memory limits, liveness probe). If one message takes long to process, the Data team can raise `max.poll.interval.ms` or lower `max.poll.records`.

Never reset the group to `--to-latest` to make the alert go away: every skipped message is an order missing from the reports.

## Escalate if
- Lag keeps growing for more than 2 hours, or the oldest unread message is older than the topic's 7-day retention will allow soon: messages will be deleted unread. This is a SEV3: tell the Data team in #data-team.
- Brokers are down or under-replicated partitions are reported. Page the Data team (see "Incident and escalation process").
