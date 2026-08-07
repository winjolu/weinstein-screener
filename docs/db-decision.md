See also docs/parameter-calibration.md for decisions about the
screener's numeric thresholds and what evidence each one rests on.

# Database Choice: SQLite (not hosted Postgres/Supabase)

## Decision
This project uses SQLite (in application support, local-only),
not a hosted database service like Supabase or managed Postgres.

## Why
- **ACID is not the deciding factor.** SQLite is fully ACID-compliant
  (atomic commits, consistency, isolation, durability), same as
  Postgres. Choosing a hosted database would not gain ACID guarantees
  I don't already have locally.
- **Usage pattern doesn't need a network database.** This is a
  single-user screener with no concurrent writers and no web
  frontend. A file-based database serves every actual read/write
  pattern this project has.
- **Attack surface.** A hosted database means a real network-facing
  endpoint, a connection string or service-role key to protect
  alongside my existing API credentials, and access-policy
  configuration that can be gotten wrong. A local file has none of
  that: nothing can reach it unless my machine itself is compromised.
- **Operational simplicity.** No service to provision, monitor, or
  lose access to if a provider shuts down (ElephantSQL's 2025
  shutdown is a concrete example of that risk materializing for a
  comparable free-tier hosted Postgres option).

## When I'd revisit this
If this project ever needs genuine concurrent multi-user access, a
live web frontend querying it directly, or scale well beyond a
personal watchlist, migrating from SQLite to Postgres is
straightforward — same relational model, no schema philosophy
change required.
