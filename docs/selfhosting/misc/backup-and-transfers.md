There are 4 places where data unique to your bot is stored:

- `config.yml` contains your basic settings
- `admin_panel/media` contains all the assets you have uploaded through the admin panel
- All data is stored in a PostgreSQL database
- Automatic backups of the database are available in `pgbackups`

## Manual backups/transfers

This is if you want to proceed to a complete backup of everything, or transfer your bot to a different machine.

First, make sure your bot is fully turned off. Do `docker compose down` if you're running Docker.

- The `config.yml` can simply be copied. Be careful not to share it as it contains your bot token!
- Same for `admin_panel/media`, you can create a zip archive with all its contents
- You can also transfer `pgbackups` if you wish to preserve backups too.

Then you must make a dump of the database.

### Creating a database dump

=== "With Docker"

    ```bash
    docker compose up -d postgres-db && \
        docker compose exec pg_dump -U ballsdex ballsdex -f data-dump.sql && \
        docker compose cp postgres-db:data-dump.sql .
    ```

=== "Without Docker"

    ```bash
    pg_dump -U ballsdex ballsdex -f data-dump.sql
    ```

This will generate a file `data-dump.sql` which you need to preserve, containing all the data.

### Importing a database dump

=== "With Docker"

    ```bash
    docker compose up -d postgres-db && \
        cat data-dump.sql | \
        docker compose exec -T postgres-db psql -U ballsdex ballsdex
    ```

=== "Without Docker"

    ```bash
    psql -U ballsdex ballsdex -f data-dump.sql
    ```

This will print a lot of lines such as `INSERT` or `ALTER TABLE`. Check the logs to ensure no errors were produced.

!!! warning

    **This only works if the database is completely empty!**

    If you messed up and wish to reset the database to redo the import,
    follow [this](#wiping-the-database).

## Restoring a backup

If you accidentally deleted something important, or your database became corrupted, you can restore a backup. They are located in the `pgbackups` folder.

First, you must [wipe the database](#wiping-the-database). Then, locate the backup file you want to use (we will assume it's named `ballsdex-latest.sql.gz` and follow the instructions according to your OS.

### macOS/Linux

=== "With Docker"

    ```bash
    docker compose up -d postgres-db && \
        zcat ballsdex-latest.sql.gz | \
        docker compose exec -T postgres-db psql -U ballsdex ballsdex
    ```

=== "Without Docker"

    ```bash
    zcat ballsdex-latest.sql.gz | psql -U ballsdex ballsdex
    ```

### Windows

Open the `ballsdex-latest.sql.gz` using [7zip](https://www.7-zip.org/) and extract the resulting `.sql` file. Move it to your bot's folder, then:

=== "With Docker"

    ```bash
    docker compose up -d postgres-db && \
        cat data-dump.sql | \
        docker compose exec -T postgres-db psql -U ballsdex ballsdex
    ```

=== "Without Docker"

    ```bash
    psql -U ballsdex ballsdex -f data-dump.sql
    ```

## Wiping the database

If you need to reset the PostgreSQL database (importing data, restoring a backup), do this:

=== "With Docker"

    ```bash
    docker compose down --volumes
    ```

=== "Without Docker"

    ```bash
    psql -U ballsdex ballsdex -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
    ```

!!! danger

    This is irreversible, be extra sure that your backups are there!
