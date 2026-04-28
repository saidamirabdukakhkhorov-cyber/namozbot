# Database notes

The schema is optimized for persistence and safe deploys. `missed_prayers` has a partial unique index on `(user_id, prayer_name, prayer_date)` where `status='active'`, which prevents duplicate active qazolar while preserving historical completed/cancelled rows.

`reminders_log` has an idempotency key over user, reminder type, related entity and scheduled time. This protects against duplicate reminders after restarts or accidental multiple app instances.

`user_states` stores flow state in PostgreSQL, not process memory.
