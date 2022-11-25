# Contributing

Thanks for contributing to this repo! This is a short guide to set you up for running Ballsdex in
a development environment, with some tips on the code structure.

## Setting up the environment

### PostgreSQL and Redis

Using Docker:

1. Install Docker.
2. Run `docker compose build` at the root of this repository.
3. Create an `.env` file like this:

   ```env
   BALLSDEXBOT_TOKEN=your discord token
   POSTGRES_PASSWORD=a random string
   ```

4. Run `docker compose up -d postgres-db redis-cache`. This will not start the bot.

----

Without docker, check how to install and setup PostgreSQL and Redis-server on your OS.
Export the appropriate environment variables as described in the
[README](README.md#without-docker).

### Installing the dependencies

1. Get Python 3.10 and pip
2. Install poetry with `pip install poetry`
3. Run `poetry install`
4. You may run commands inside the virtualenv with `poetry run ...`, or use `poetry shell`
5. Set up your IDE Python version to the one from Poetry. The path to the virtualenv can
   be obtained with `poetry show -v`.

## Running the code

### Starting the bot

- `poetry shell`
- ```bash
  BALLSDEXBOT_DB_URL="postgres://ballsdex:password@localhost:5432/ballsdex" \
  python3 -m ballsdex --dev --debug
  ```

Replace `password` with the same value as the one in the `.env` file.
If appropriate, you may also replace `localhost` and `5432` for the host and the port.

### Starting the admin panel

**Warning: You need to run migrations from the bot at least once before starting the admin
panel without the other components.**

If you're not actively working on the admin panel, you can just do `docker compose up admin-panel`.
Otherwise, follow these instructions to directly have the process without rebuilding.

- `poetry shell`
- ```bash
  BALLSDEXBOT_DB_URL="postgres://ballsdex:password@localhost:5432/ballsdex" \
  BALLSDEXBOT_REDIS_URL="redis://127.0.0.1" \
  python3 -m ballsdex --dev --debug
  ```

Once again, replace `password` with the same value as the one in the `.env` file.
If appropriate, you may also replace `localhost` and `5432` for the host and the port.

## Migrations

When modifying the Tortoise models, you need to create a migration file to reflect the changes
everywhere. For this, we're using [aerich](https://github.com/tortoise/aerich).

### Applying the changes from remote

When new migrations are available, you can either start the bot to run them automatically, or
execute the following command:

```sh
BALLSDEXBOT_DB_URL="postgres://ballsdex:password@localhost:5432/ballsdex" \
aerich upgrade
```

Once again, replace `password` with the same value as the one in the `.env` file.
If appropriate, you may also replace `localhost` and `5432` for the host and the port.

### Creating new migrations

If you modified the models, `aerich` can automatically generate a migration file.

**You need to make sure you have already ran previous migrations, and that your database
is not messy!** Aerich's behaviour can be odd if not in ideal conditions.

Execute the following command to generate migrations, and push the created files:

```sh
BALLSDEXBOT_DB_URL="postgres://ballsdex:password@localhost:5432/ballsdex" \
aerich migrate
```

## Coding style

The repo is validating code with `flake8` and formatting with `black`. They can be setup as a
pre-commit hook to make them run before committing files:

```sh
pre-commit install
```

You can also run them manually:

```sh
pre-commit run -a
```
