# SRA V2 Database

The SRA V2 architecture uses a new PostgreSQL database named `sra_v2_db`.

The legacy `sra_db` database contains development and test data and must not be migrated, modified, truncated, or deleted as part of the V2 setup.

## Database separation

- Legacy system database: `sra_db`
- New SRA V2 database: `sra_v2_db`
- Legacy data migration: intentionally not supported
- Initial V2 inventory: empty
- Physical storage capacity: 30 slots (`S01` through `S30`)

## Create the new database

Run the bootstrap script from a PostgreSQL maintenance database using an account that can create databases:

```bash
psql -d postgres -f database/bootstrap/001_create_sra_v2_database.sql
```

The script creates `sra_v2_db` only when it does not already exist. It does not alter `sra_db`.

## Initialize the V2 schema

```bash
psql -d sra_v2_db -f database/migrations/001_digital_twin_foundation.sql
```

The initial schema creates:

- Festo State Code catalog and valid transitions
- physical carriers
- physical fuse-box parts/digital twins
- inspection history
- production process history
- 30 ROS2-managed storage slots
- digital-twin and physical-inventory read views

No rows are copied from the legacy database.

## Runtime configuration

New V2 components use dedicated environment variables:

```bash
SRA_V2_DB_HOST=localhost
SRA_V2_DB_NAME=sra_v2_db
SRA_V2_DB_USER=sra_user
SRA_V2_DB_PASSWORD=<password>
SRA_V2_DB_PORT=5432
```

Legacy components continue using the existing `SRA_DB_*` variables until they are retired or migrated to the V2 architecture.
