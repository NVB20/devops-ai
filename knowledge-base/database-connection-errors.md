# Database connection errors

## Symptoms
Applications log errors like:
- `connection refused` or `could not connect to server`
- `timeout expired` or `connection timed out`
- `FATAL: sorry, too many clients already` or `remaining connection slots are reserved`
- `FATAL: password authentication failed for user`
- `could not translate host name to address`
- `SSL connection is required` or `no pg_hba.conf entry for host`

The service returns 500 errors, health checks fail, and pods may restart.

## Likely causes
- PostgreSQL is down, restarting, or in the middle of a failover.
- The connection limit is reached: a connection leak, or too many replicas × pool size. In `prod`, `max_connections` is 200 and all apps should connect through PgBouncer.
- PgBouncer itself is down or its pool is full.
- Credentials were rotated but the app still uses the old ones.
- Network problems: a Kubernetes NetworkPolicy, firewall or security group blocks port 5432.
- DNS can't resolve the database host name.
- Long-running queries or locks block new work, so the pool fills up.

## How to diagnose
From inside an application pod, check that the database is reachable:

```bash
kubectl exec -it <pod-name> -n <namespace> -- sh
nslookup <db-host>
nc -zv <db-host> 5432
pg_isready -h <db-host> -p 5432
```

If you have access to the database, check connections:

```sql
SHOW max_connections;
SELECT count(*) FROM pg_stat_activity;

-- who is using the connections
SELECT usename, application_name, state, count(*)
FROM pg_stat_activity
GROUP BY 1, 2, 3
ORDER BY 4 DESC;

-- the longest running queries
SELECT pid, now() - query_start AS duration, state, left(query, 80) AS query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY duration DESC
LIMIT 10;
```

Do the math: number of replicas × pool size per replica must stay below `max_connections`. For example, orders-api with 4 replicas and a pool of 20 uses up to 80 connections.

## Fix
- **Too many connections:** find the application with the most connections, lower its pool size or fix the leak, and make sure it connects through PgBouncer. As a short-term fix you can close old idle connections:
  ```sql
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE state = 'idle' AND state_change < now() - interval '10 minutes';
  ```
- **Slow or stuck queries:** first try `SELECT pg_cancel_backend(<pid>);`. Use `pg_terminate_backend(<pid>)` only if cancel doesn't work.
- **Password authentication failed:** the app has old credentials. Update the value in the secret manager, let it sync to the Kubernetes Secret, then run `kubectl rollout restart deployment/<name>`. Never put the password in a ticket, chat or document.
- **Network blocked:** check recent changes to NetworkPolicies and security groups.
- **Database down:** check the database dashboard and the provider status page, and wait for or trigger the failover.

## Escalate if
- The primary database is down or the failover didn't complete. Page the Data team on-call and declare a SEV1 (see "Incident and escalation process").
- You see signs of data corruption or replication lag that keeps growing.
- You think `max_connections` needs to change. This needs a database restart, so the Data team must plan it.
