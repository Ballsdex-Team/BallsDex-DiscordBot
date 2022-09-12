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
   BALLSDEXBOT_DB_PASSWORD=a random string
   ```

4. Run `docker compose up -d db redis-cache`. This will not start the bot.

----

Without docker, check how to install and setup PostgreSQL and Redis-server on your OS.
Export the appropriate environment variables as described in the
[README](README.md#without-docker).

### Installing the dependencies

1. Get Python 3.10 and pip
2. Install poetry with `pip install poetry`
3. Run `poetry install --dev`
4. You may run commands inside the virtualenv with `poetry run ...`, or use `poetry shell`
5. Set up your IDE Python version to the one from Poetry. The path to the virtualenv can
   be obtained with `poetry show -v`.

### Running the bot

`poetry run python3 -m ballsdex --dev --debug`

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
