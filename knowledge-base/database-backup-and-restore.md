# Database backup and restore procedure

## Backup setup
- **What:** the prod PostgreSQL cluster (orders, customers, payments).
- **How:** a full backup every night at 02:00 UTC, plus continuous WAL archiving. Together they allow point-in-time recovery (PITR) to any moment in the last 30 days.
- **Where:** object storage in a different region from the database. Backups are encrypted, and only the Data team and the backup service account can read them.
- **Targets:** RPO (maximum data loss) is 5 minutes. RTO (time to restore) is 1 hour.
- **Testing:** every month the Data team restores the latest backup to a test instance and records the result.
- **Owner:** the Data team. Only the Data team runs restores in prod.

## When to restore
- Data was deleted or corrupted by a bad release, a bad migration or a manual mistake.
- Both the primary and the replica are lost.
- A copy is needed for an investigation, for example after a security incident.

Most problems that look like "the database is broken" are not fixed by a restore. Check "Database connection errors" first.

## Check backup health
```sql
SELECT archived_count, failed_count, last_archived_wal, last_archived_time, last_failed_time
FROM pg_stat_archiver;
```

`last_archived_time` should be within the last few minutes, and `failed_count` should not be going up. The alert "PostgreSQL backup older than 26 hours" fires if a nightly backup is missing.

## How to restore
1. Declare an incident (see "Incident and escalation process") and page the Data team. A prod restore is at least a SEV2.
2. Stop the damage: roll back the bad release, or pause the job that is deleting data.
3. Agree on the target time, the last moment before the problem started. Use the application logs and the deploy time posted in #deployments.
4. Restore to a **new** instance at that point in time. Never restore over the running primary.
5. Check the restored data: row counts, the latest orders, and the specific records that were lost.
6. Choose how to recover:
   - **Small loss (some rows, or one table):** copy the missing data from the restored instance into prod.
     ```bash
     pg_dump -Fc -h <restored-host> -d orders -t <table> -f table.dump
     pg_restore --list table.dump
     pg_restore -h <prod-host> -d orders --data-only -t <table> table.dump
     ```
     A data-only restore can conflict with rows that already exist. If you're not sure, restore into a scratch database first and copy the missing rows with SQL.
   - **Large loss:** point the applications to the restored instance by updating the database host in the secret manager and Helm values, then restart the apps. Orders written after the target time will be missing, so export them from the old primary first.
7. When you're finished, delete dump files from laptops and pods. They contain customer data.

## Escalate if
- Backups are missing, or the last good backup is older than the RPO.
- The restore fails or takes longer than 1 hour.
- You suspect the data loss was caused by an attack. Contact the Security team before changing anything, so evidence is kept (see "Suspected compromised host or container").
