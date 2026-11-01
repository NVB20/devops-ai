# Docker container won't start or keeps restarting

## Symptoms
- `docker ps` shows the container as `Restarting (1) 5 seconds ago`.
- The container is missing from `docker ps`, but `docker ps -a` shows it as `Exited (1)` or `Exited (137)`.
- `docker compose up` prints "exited with code 1" for a service.
- The health check shows `unhealthy`, or the app on the mapped port doesn't respond.

## Likely causes
- The application crashes on startup (bad config, missing environment variable, code error).
- The host port is already in use: `bind: address already in use`.
- A volume mount points to the wrong path, or the container user can't read or write it (`permission denied`).
- The image was built for a different CPU architecture: `exec format error`.
- The container runs out of memory and is killed (exit code 137, `OOMKilled: true`).
- A container it depends on (database, cache) isn't ready yet. `depends_on` only waits for the container to start, not for it to be ready.
- The restart policy (`always` or `unless-stopped`) hides a crash loop by restarting forever.

## How to diagnose
```bash
docker ps -a
docker logs --tail 100 <container>
docker inspect <container> --format 'status={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}'
docker events --since 10m --filter container=<container>
```

For Docker Compose:

```bash
docker compose ps
docker compose logs --tail 100 <service>
docker compose config   # shows the final config after .env values are applied
```

To see the error yourself, start a shell in the image instead of the normal command:

```bash
docker run --rm -it --entrypoint sh <image>
```

Check if the port is already taken on the host:

```bash
ss -ltnp | grep <port>          # Linux
netstat -ano | findstr <port>   # Windows
```

## Fix
- **Crash in the app:** read the first error in `docker logs` (not the last one), fix the config or code, rebuild and start again.
- **Port in use:** stop the other process, or map a different host port (`-p 8081:8000`).
- **Missing environment variable:** add it to the compose file or `.env`. Don't bake secrets into the image.
- **Volume permissions:** make the host directory owned by the user ID the container runs as: `chown -R <uid>:<gid> <dir>`.
- **exec format error:** rebuild for the right platform: `docker buildx build --platform linux/amd64 -t <image> .`
- **Out of memory:** raise the memory limit (`--memory` or `mem_limit`) or fix the leak.
- **Dependency not ready:** add a `healthcheck` to the dependency and use `depends_on` with `condition: service_healthy`. The app should also retry its connections.
- To stop the restart loop while you investigate: `docker update --restart=no <container>`.

## Escalate if
- The Docker daemon itself is unhealthy: `docker ps` hangs or the daemon keeps restarting. Contact the Platform team.
- The host disk is full (see "Disk full on a server").
- The image belongs to another team and the crash is in their code. Contact the owning team (see "Service overview and architecture").
