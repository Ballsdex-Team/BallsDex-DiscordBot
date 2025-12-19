This guide will help you upgrade from 2.X to Ballsdex 3.0.

!!! warning
    Ballsdex 3.0 brings a lot of breaking changes!

    If you have modifications or custom packages, you must remove them before upgrading. Once
    you have upgraded, you can look for the updated version of your packages.

## 1. Pre-requirements and disclaimers

- There must be no custom package. Remove any custom package you may have, and only after the bot
  migration you may look into migrating them.
- If you are relying on eval to run your bot, be aware that they will most likely break and
  need to be rewritten.
- The output of `git status` must show **no modified or untracked files**!
    - If you have files listed there, copy the modifications and run `git reset --hard HEAD`
- You must be running on the latest 2.X version
    - Run a normal update and restart your bot once to ensure you're up-to-date.
- For Docker users, you must have Docker Compose version 2.39.4 at least.
  Run `docker compose version` to check, and upgrade if necessary.
  
    If you followed the initial install instructions on Ubuntu,
    `sudo apt update && sudo apt upgrade` should be enough.

- If you're running nginx locally, ditch your configuration. It's now included in Docker.
- If you have a list of admins on the admin panel that you wish to preserve, be prepared to back
  them up. The admins will be wiped and won't be recovered during the migration.
- Turn off your bot now

    === "With Docker"
  
        ```bash
        docker compose down
        ```
  
    === "Without Docker"
  
        Just do Ctrl+C on both your bot and the admin panel

## 2. Perform a backup

**This is the most important step!** The database will be wiped later.

=== "With Docker"

    ```bash
    docker compose up -d postgres-db --wait && \
        docker compose exec postgres-db pg_dump -U ballsdex ballsdex -f data-dump.sql && \
        docker compose cp postgres-db:data-dump.sql pre-migration-data-dump.sql
    ```

=== "Without Docker"

    ```bash
    pg_dump -U ballsdex ballsdex -f pre-migration-data-dump.sql
    ```

Triple-check that there is a `pre-migration-data-dump.sql` file and that it's not empty!
You may also want to copy it to different locations just to be sure.

## 3. Prepare your data for the migration

For the migration to work successfully, we need to drop multiple tables related to Django
authentication.

!!! warning
    **Past this point, you will lose all of your administrators configured on the admin panel.**

    It most likely matters little for 95% of you, the admins can be re-created later in a few
    seconds. However, if you have spent a long time adding a lot of admins with custom permissions,
    you may want to write down those information.

Run the following commands to wipe a selection of tables, then create a new backup.

=== "With Docker"

    ```bash
    docker compose up -d postgres-db --wait && \
        docker compose run --rm migration python3 manage.py migrate admin zero && \
        docker compose run --rm migration python3 manage.py migrate auth zero && \
        docker compose run --rm migration python3 manage.py migrate contenttypes zero && \
        docker compose run --rm migration python3 manage.py migrate sessions zero && \
        docker compose exec postgres-db pg_dump -U ballsdex ballsdex -f data-dump.sql && \
        docker compose cp postgres-db:data-dump.sql final-data-dump.sql
    ```

=== "Without Docker"

    ```bash
    # activate your venv and export BALLSDEXBOT_DB_URL
    cd admin_panel
    python3 manage.py migrate admin zero
    python3 manage.py migrate auth zero
    python3 manage.py migrate contenttypes zero
    python3 manage.py migrate sessions zero

    pg_dump -U ballsdex ballsdex -f final-data-dump.sql
    ```

You now have two files: `pre-migration-data-dump.sql` and `final-data-dump.sql`
- `pre-migration` must be used if you wish to roll back to 2.X, it's an unmodified backup
- `final` must be used for the following steps. **Do not use it to roll back to 2.X, it won't work!**

### Wipe the database

This only applies to Docker users.

3.0 upgrades the database to Postgres 18. A major upgrade of Postgres implies a deletion
of the database, which will be imported later from your backup.

!!! warning
    Are you 100% sure you have backed everything up?
    Check again now that `pre-migration-data-dump.sql` exists.

Run the following command to delete your database.

```bash
docker compose down --volumes
```

## 4. Perform the upgrade

=== "With Docker"

    1.  Switch to the new branch
        ```bash
        git switch v3
        git pull
        ```
    2.  Create the new database
        ```bash
        docker compose up -d postgres-db --wait
        ```
    3.  Import your database dump
        ```bash
        cat final-data-dump.sql | docker compose exec -T postgres-db psql -U ballsdex ballsdex
        ```
    4.  Rebuild the bot
        ```bash
        docker compose build
        ```
    5.  Run migrations
        ```bash
        docker compose up migration
        ```

=== "Without Docker"

    1.  Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
        !!! info
            You can [uninstall Poetry](https://python-poetry.org/docs/#installation) if you want,
            it's not needed anymore.
    2.  Switch to the new branch
        ```bash
        git switch v3
        git pull
        ```
    3.  Install the new virtual environment
        ```bash
        uv sync
        ```
        !!! note
            Python 3.14 is required to run Ballsdex 3.0. If it's not installed on your system,
            uv will install it for you.
    4.  Activate the new virtual environment

        === "Linux/macOS"
            ```bash
            source .venv/bin/activate
            ```
        
        === "Windows (PowerShell)"
            ```ps1
            . .\.venv\Scripts\activate.ps1
            ```

    5.  Export the usual environment vars

        === "Linux/macOS"
            ```bash
            export BALLSDEXBOT_DB_URL=postgres://username:password@localhost:5432/database_name
            ```
        
        === "Windows (PowerShell)"
            ```ps1
            $Env.BALLSDEXBOT_DB_URL = 'postgres://username:password@localhost:5432/database_name'
            ```

    6.  Run the migrations
        ```bash
        cd admin_panel && python3 manage.py migrate
        ```

## 5. Reconfigure the settings

Ballsdex 3.0 does not use `config.yml` anymore for its configuration, instead it's all on the
admin panel. You can still import your old settings.

1.  [Create a local admin account](/selfhosting/admin-panel/getting-started/).
    Remember that all admin accounts were lost in the process, you have to recreate one.
2.  Start the admin panel

    === "With Docker"

        ```bash
        docker compose up -d proxy
        ```

        !!! note
            Don't start the admin panel with `admin-panel` service anymore, use `proxy` instead.

    === "Without Docker"

        After having activated your venv and exported the env vars
        
        === "Linux/macOS"
            ```bash
            export DJANGO_SETTINGS_MODULE="admin_panel.settings.dev"
            cd admin_panel && uvicorn admin_panel.asgi:application
            ```
        
        === "Windows (PowerShell)"
            ```ps1
            $Env.DJANGO_SETTINGS_MODULE = 'admin_panel.settings.dev'
            cd admin_panel && uvicorn admin_panel.asgi:application
            ```
        
        !!! note
            You are running the admin panel in developer mode as the default configuration
            does not serve static files anymore. Docker handles it via a pre-configured nginx
            proxy.

            You will have to find a solution later to expose the static files yourself.

3.  Open [the new settings page](http://localhost:8000/settings/settings/)
4.  Tick the checkbox next to "Global bot settings"
5.  In the "Action" drop-down, select "Import YAML settings" and click "Go"
6.  Choose the `config.yml` file to upload, and continue
7.  Verify that all the settings were imported as intended.

!!! warning
    This will override settings you have previously configured here.

---

You're all good! You can now start your bot again.
