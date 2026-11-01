# Disk full on a server

## Symptoms
- Errors like `No space left on device` in application or system logs.
- Writes fail: uploads, log files, database inserts, Docker image pulls.
- Services crash or refuse to start. PostgreSQL may switch to read-only or shut down.
- Alert "Disk usage above 90%" fires for a host or a persistent volume.
- `df -h` shows free space but writes still fail. This means the filesystem has run out of inodes (usually millions of tiny files).

## Likely causes
- Logs are not rotated, or one application writes huge debug logs.
- Old Docker images, stopped containers, unused volumes and build cache.
- Core dumps from crashing processes.
- Large temporary files or local backups left on the server.
- Files that were deleted but are still held open by a running process, so the space is not freed.
- Database WAL files growing because replication or archiving is stuck.

## How to diagnose
Find which filesystem is full, then which directory is using the space:

```bash
df -h
df -i                                   # inode usage
du -xsh /var/* 2>/dev/null | sort -h
du -xsh /var/log/* 2>/dev/null | sort -h | tail -20
find / -xdev -type f -size +500M -exec ls -lh {} \; 2>/dev/null
```

Check the usual suspects:

```bash
docker system df                        # space used by images, containers, volumes, cache
journalctl --disk-usage                 # systemd journal size
ls -lh /var/crash /var/lib/systemd/coredump 2>/dev/null
sudo lsof +L1                           # deleted files still held open
```

If `df` says the disk is full but `du` can't find the files, the answer is almost always a deleted file that is still open (`lsof +L1`).

## Fix
- **Big active log file:** empty it in place with `truncate -s 0 /var/log/<app>/<file>.log`. Do not `rm` it while the process is running, because the space is not freed until the process closes the file.
- **Systemd journal:** `sudo journalctl --vacuum-size=500M`.
- **Log rotation:** check the config in `/etc/logrotate.d/` and test it with `sudo logrotate -d /etc/logrotate.conf`.
- **Docker:** remove what is not in use:
  ```bash
  docker container prune
  docker image prune -a
  docker builder prune
  ```
  Be careful with `docker volume prune`: it deletes volume data permanently.
- **Docker container logs:** set a limit in `/etc/docker/daemon.json` (`"log-opts": {"max-size": "50m", "max-file": "3"}`) so it doesn't happen again.
- **Deleted but open files:** restart the process that holds them (shown by `lsof +L1`).
- **Core dumps:** keep one for the developers, delete the rest.
- **Long term:** resize the volume, or move logs and backups to object storage.

Never delete files inside the database data directory (for example `/var/lib/postgresql`) to free space. This can corrupt the database.

## Escalate if
- The full disk is on a database server. Contact the Data team on-call before you delete anything.
- The volume needs to be resized in the cloud provider and you don't have access. Contact the Platform team.
- Usage grows back quickly after cleanup, which means something is actively writing. Find the process and contact the owning team.
- A production service is down because of the full disk. Declare an incident (see "Incident and escalation process").
