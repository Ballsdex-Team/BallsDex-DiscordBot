# Migrating to WSL (Windows)

As Docker for Windows has a LOT of errors that are hardly fixable, it is now discouraged to host Ballsdex on Windows. The recommended way is to host on Linux, which is possible on Windows with WSL.

This guide will show how to migrate your bot to WSL and ditch Docker for Windows.

## 1. Backup and uninstall

Follow [this guide](backup-and-transfers.md) to backup your data. In theory, you only need the `data-dump.sql` file, but better be safe.

Once this step is complete and you have verified the contents of your database dump, **uninstall Docker Desktop** from Windows. You must still keep the bot's folder.

!!! tip
    WSL can use more disk space. If you have less than 30GB available, it is a good idea to clean your computer now.

## 2. Configure WSL

Follow [the first part of the new tutorial](../installation/installing-ballsdex.md) to install WSL and Docker. Don't forget the last step to test and confirm that your new Docker works.

## 3. Locate the bot's folder

You don't need to clone the bot again, WSL is able to access your Windows files.

Open your BallsDex-DiscordBot folder in the file explorer, then in the explorer bar (top left), click and write `wsl` (instead of `cmd` or `powershell` this time). This will open a terminal inside WSL, where your files are accessible.

Every time you need to type shell commands for the bot, you need to do the step above.

## 4. Import your database dump

!!! warning
    **Do NOT start the bot yet!** It will mess everything up by re-creating an empty database

1. Type `docker compose up -d postgres-db` to only start the database and nothing else.
2. Run `cat data-dump.sql | docker compose exec -T psql -U ballsdex ballsdex`
3. This will print a lot of lines such as `INSERT` or `ALTER TABLE`. Check the logs to ensure no errors were produced before continuing.

## 5. Build and start the bot

Run `docker compose build` to build the image.

Then follow [this section](../installation/installing-ballsdex.md#6-run-the-bot) to start your bot. You shouldn't need any configuration, the bot will pick up your old files and resume just like before.

## 6. Using Docker on Linux

There is no more Docker Destkop to view your containers, everything goes through the command line, so have the following reminder:

- Start your bot: `docker compose up -d`
- Stop your bot: `docker compose down`
- Check if your bot is running: `docker compose ps` (look for a line that says `ballsdex-discordbot-bot-1`)
- View logs: `docker compose logs`
- View logs from the bot only: `docker compose logs bot`
- View logs from the admin panel: `docker compose logs admin-panel`
- View live logs from the bot: `docker compose logs bot -f` (press Ctrl+C to exit)
- Quick restart the bot: `docker compose restart bot` (useful after changing config, do not do this after updates)