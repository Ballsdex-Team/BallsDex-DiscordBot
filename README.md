# BallsDex Discord Bot

[![Discord server](https://discordapp.com/api/guilds/1049118743101452329/embed.png)](https://discord.gg/Qn2Rkdkxwc)
[![Pre-commit](https://github.com/laggron42/BallsDex-DiscordBot/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/laggron42/BallsDex-DiscordBot/actions/workflows/pre-commit.yml)
[![Docker build](https://github.com/laggron42/BallsDex-DiscordBot/actions/workflows/docker.yml/badge.svg)](https://github.com/laggron42/BallsDex-DiscordBot/actions/workflows/docker.yml)
[![CodeQL](https://github.com/laggron42/BallsDex-DiscordBot/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/laggron42/BallsDex-DiscordBot/actions/workflows/codeql-analysis.yml)
[![Issues](https://img.shields.io/github/issues/laggron42/BallsDex-DiscordBot)](https://github.com/laggron42/BallsDex-DiscordBot/issues)
[![discord.py](https://img.shields.io/badge/discord-py-blue.svg)](https://github.com/Rapptz/discord.py)
[![Black coding style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)
[![Patreon](https://img.shields.io/badge/Patreon-donate-orange.svg)](https://patreon.com/retke)

BallsDex is a bot for collecting countryballs on Discord and exchange them with your friends!

You can invite the bot [here](https://discord.com/api/oauth2/authorize?client_id=999736048596816014&permissions=537193536&scope=bot%20applications.commands).

[![Discord server](https://discordapp.com/api/guilds/1049118743101452329/embed.png?style=banner3)](https://discord.gg/Qn2Rkdkxwc)

## Suggestions, questions and bug reports

Feel free to ask any question on the Discord server above, we'll be here for discussing about your
issue. If we estimate that your issue is important, you may be invited to post here instead (or
we'll do it for you).

You can directly post an issue in this repo, be sure to use the template!

## Running the bot

The bot comes as a [poetry](https://python-poetry.org/) Python package and can run using Docker.

You must first setup a Discord bot. **No privileged intents are required!**

### With Docker (recommended)

1. Install Docker on your machine. We assume you have the correct permissions to run commands.
2. At the root of the repository, run `docker compose build`
3. Add a text file `.env` at the root of the repository in the following form:

   ```env
   BALLSDEXBOT_TOKEN=your token here
   POSTGRES_PASSWORD=a random string
   ```

4. Run the bot with `docker compose up -d`

The bot will be running in detached mode. You can view the logs with `docker compose logs -f`.

If you want to shutdown the bot, run `docker compose down`.

When updating the bot, do the following:

1. `git pull`
2. `docker compose build`
3. `docker compose down && docker compose up -d`

### Without Docker

**This part is not supported.** I use docker myself for production, and run the `db` and
`redis-cache` services from `docker-compose` for development.

We assume that you have Python 3.10 and pip installed.

1. Start a PostgreSQL server on the host.
   1. Create a postgres user and database.
2. Start a Redis serve on the host.
3. Install poetry with `pip install poetry`.
4. Run `poetry install`
5. Export the following environment variables:

   - `BALLSDEXBOT_TOKEN`: the Discord bot token
   - `BALLSDEXBOT_DB_URL`: a link in the form `postgres://{postgres user name}:{postgres password}@localhost:5432/{database name}`
   - `BALLSDEXBOT_REDIS_URL`: a link in the form `redis://localhost`

   Replace `localhost` with any host when appropriate.

6. Run `poetry run python3 -m ballsdex`

There are some command line options available when starting the bot.
See them with `python3 -m ballsdex --help`.

## Contributing

Take a look at [the contribution guide](CONTRIBUTING.md) for setting up your environment!

## License

This repository is released under the [MIT license](https://opensource.org/licenses/MIT).

If distributing this bot, credits to the original authors must not be removed.
