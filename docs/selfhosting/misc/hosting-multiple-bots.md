Hosting multiple bots on one machine is very similar to hosting one.

First, enter a Linux terminal (WSL or proper linux).

## 1. Download the bot
Clone Ballsdex. **You must replace <botname>** with some text you haven't already used for another bot (the dex's name is a decent choice)

```bash
git clone https://github.com/laggron42/BallsDex-DiscordBot.git <botname>
```

Then, run `cd <botname>` (replacing <botname> with whatever you chose). Like with one bot, every time you need to type commands for a dex, you must always open the bot's directory first.

!!! warning
    You must not change your bot's folders name after installation. Doing so will result in your dex being unable to find your config and data.

## 2. Change the port
If you do not change the port for the new bot, they will collide and the new bot won't be able to run.

Create a file with the name `docker-compose.override.yml` using this command:
```bash
touch docker-compose.override.yml
```

Using an editor of your choice, open the file and insert:
```yaml
services:
  proxy:
    ports: !override
      - "127.0.0.1:8001:80"
```

If you are running a 3rd or even more bots, change `8001` to `8000+number of bots` or just pick a number you haven't used yet.

!!! info
    You may have seen some people suggesting editing the docker-compose.yml to change the port. While this will work, using an override is better because then the git tree is clean (`docker-compose.override.yml` is gitignored)

## 3. Setting up the bot
From here, the process is the same as with a normal bot. Continue with [the rest of the tutorial](../installation/installing-ballsdex.md#4-installing-the-bot).
