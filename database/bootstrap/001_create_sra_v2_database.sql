\set ON_ERROR_STOP on

-- Create the new production database without modifying or deleting the legacy
-- test database. This script must be executed from a maintenance database such
-- as postgres by a role allowed to create databases.
--
-- Expected existing application role: sra_user

SELECT 'CREATE DATABASE sra_v2_db OWNER sra_user ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_database
    WHERE datname = 'sra_v2_db'
)\gexec
