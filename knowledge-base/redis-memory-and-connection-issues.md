# Redis out of memory or connection errors

## Symptoms
Applications, mostly orders-api, log errors like:
- `OOM command not allowed when used memory > 'maxmemory'`
- `ERR max number of clients reached`
- `LOADING Redis is loading the dataset in memory`
- connection timeouts, or `Connection reset by peer`

Pages get slower because the product cache misses, and users may be logged out because sessions are stored in Redis.

## Likely causes
- Keys are written without a TTL, so memory grows until it reaches `maxmemory`.
- The eviction policy is `noeviction`, so Redis rejects writes instead of removing old keys.
- A few very large keys (big lists, sets or hashes).
- A connection leak, or many replicas that each open a large connection pool.
- Slow commands block Redis, because it runs commands one at a time: `KEYS *`, a large `SMEMBERS`, `FLUSHALL`.
- Redis restarted and is still loading its data from disk.

## How to diagnose
Connect with `redis-cli` from a pod in the same namespace. Pass the password through the `REDISCLI_AUTH` environment variable, filled from the Kubernetes Secret. Don't use `-a <password>`, because it ends up in shell history and in the process list.

```bash
redis-cli -h <redis-host> INFO memory       # used_memory_human, maxmemory_human, maxmemory_policy
redis-cli -h <redis-host> INFO clients      # connected_clients
redis-cli -h <redis-host> INFO stats        # evicted_keys, rejected_connections
redis-cli -h <redis-host> CONFIG GET maxclients
redis-cli -h <redis-host> SLOWLOG GET 10
redis-cli -h <redis-host> --bigkeys
redis-cli -h <redis-host> --latency
```

Find which clients hold the most connections:

```bash
redis-cli -h <redis-host> CLIENT LIST | awk '{print $2}' | cut -d: -f1 | sort | uniq -c | sort -rn | head
```

Map the IP addresses to pods with `kubectl get pods -n prod -o wide`.

Never run `KEYS *` in prod. It blocks Redis while it scans every key. Use `SCAN` instead.

## Fix
- **Out of memory:** for the cache, use `maxmemory-policy allkeys-lru` so old keys are evicted. Make sure every cache key is written with a TTL, for example `SET <key> <value> EX 3600`. If the data really needs more space, ask the Data team to raise `maxmemory`.
- **Big keys:** split them into smaller keys. Delete them with `UNLINK`, which doesn't block, instead of `DEL`.
- **Too many clients:** find the app with the most connections, lower its pool size or fix the leak, and make sure it closes connections on shutdown.
- **Slow commands:** find them in `SLOWLOG` and replace them in the code, for example with `SCAN`-based loops.
- **Emergency:** Redis data for the Orders platform can be rebuilt, so `FLUSHALL ASYNC` is allowed, but it logs every user out. Get approval from the incident commander and the Data team first.

## Escalate if
- Redis is down or keeps restarting. Page the Data team. This is a SEV2 (see "Service overview and architecture").
- Memory keeps growing even with TTLs and eviction in place.
