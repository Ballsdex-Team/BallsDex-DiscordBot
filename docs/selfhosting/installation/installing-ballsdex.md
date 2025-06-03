Ballsdex is an open source Discord bot for catching countryballs, which you can install yourself and customize!

While it can run on all operating systems, it is highly recommended to host Ballsdex on Linux (macOS mostly works the same as well). The recommended distribution we will use through this tutorial is **Ubuntu 24.04**.

## (Windows only) Installing WSL

Windows can easily run Linux distributions thanks to [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) (Windows Subsystem for Linux). You must be running Windows 10 version 2004 and higher (Build 19041 and higher) or Windows 11.

!!! info
    You need about 30GB of free space on your main disk. Check now that you have enough space.

To install Ubuntu, press Win+X and click "PowerShell (administrator)" then run the following command:

```ps
wsl --install
```

This will take a while, and may require a restart of your PC. Once it is installed, search "Ubuntu" in Windows to open the Linux shell. You will be asked a password on first start.

## 1. Install requirements

To run Ballsdex, we need Docker and git.

!!! warning
    Throughout this tutorial, you will need to type a lot of commands. You need to check each command's output and verify that it doesn't produce any error.  
    If you suspect a command failed and errored, **do not keep going** and fix the errors first.

1. Type the following commands in your Linux terminal **one by one** to proceed.  
   You will be asked to type the password you have chosen earlier to continue. What your type will be hidden but don't worry, keep typing and press enter, it will work.  
   *If your terminal doesn't let you paste text with Ctrl+V, try right clicking instead.*
   ```bash { .copy }
   sudo apt update
   sudo apt install -y git apt-transport-https ca-certificates curl software-properties-common
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt update
   apt-cache policy docker-ce
   sudo apt install -y docker-ce
   ```

    At this point, you should have Docker running.

2. Verify that Docker is running with `sudo systemctl status docker`, you should have an output like this:
   ```text
   ● docker.service - Docker Application Container Engine
        Loaded: loaded (/lib/systemd/system/docker.service; enabled; vendor preset: enabled)
        Active: active (running) since Fri 2022-04-01 21:30:25 UTC; 22s ago
   TriggeredBy: ● docker.socket
          Docs: https://docs.docker.com
      Main PID: 7854 (dockerd)
         Tasks: 7
        Memory: 38.3M
           CPU: 340ms
        CGroup: /system.slice/docker.service
                └─7854 /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock
   ```
   Press `q` to exit this screen.

3. Give your user the docker group. This will avoid having to use `sudo` every time you use Docker.
   ```bash { .copy }
   sudo usermod -aG docker ${USER}
   su - ${USER}
   ```

4. Verify Docker is working by running a test
   ```bash { .copy }
   docker run hello-world
   ```
   You should see a welcome message from Docker if everything installed successfully!

!!! tip
    If you are running macOS, you can use [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/) instead.

## 2. Create a Discord bot account

You must first setup a Discord bot account. You can follow [discord.py's tutorial](https://discordpy.readthedocs.io/en/latest/discord.html) to create and invite your bot.

For now, don't copy your token, but keep the page open.

Once this is configured, you also **need to enable message content intent**. Go to the "Bot" tab of your application, scroll down to "Privileged intents" and tick "Message content".

!!! info
    You can fill the description of your application, it will appear under the "About me" section.

## 3. Download the bot

Type the following command to download the latest version of the bot:
```bash { .copy }
git clone https://github.com/laggron42/BallsDex-DiscordBot.git
```

Then you can use the command `cd` to change directory and open the folder you just downloaded:
```bash { .copy }
cd BallsDex-DiscordBot
```

From this point, every time you need to type commands for Ballsdex, **you must always open the bot's directory first**.

!!! question "Navigating files"
    If you want to explore the files and folders with a graphical interface, you can use the following commands to bring up your system's explorer:

    - Windows (WSL): `explorer.exe .`
    - macOS: `open .`
    - Linux: `xdg-open .`

    It will be useful later when we'll need to edit files. **Do not forget the trailing dot of each command**, otherwise it won't open the correct directory.

## 4. Installing the bot

1. Run `docker compose build`. This will also take some time, wait for the build to complete.
2. Run `docker compose up bot` to generate the default configuration file. Skip this step if you already have a `config.yml` file. The following text should appear:

   ![image](https://user-images.githubusercontent.com/23153234/227784222-060decdf-87c0-46c8-a69c-1f339bf90d9e.png)

The process should exit afterwards. If it doesn't, hit `Ctrl+C`.

## 5. Configure the bot

Open the new `config.yml` file with the editor of your choice. I recommend using [Visual Studio Code](https://code.visualstudio.com/) to get autocompletion and error highlighting. Once installed, you can run `code config.yml` to open VScode from your terminal (even in WSL).

!!! info
    In YAML files, everything after a `#` is a comment. Those lines are here to document and help you understand the possible values.

1. Go back to the Discord developer portal and click "Reset Token" to obtain a new one. Copy and paste it right after `discord-token: `. Make sure that there is a space between `discord-token:` and your token, otherwise it will not work.

!!! danger
    **Do not share your token!** It is the password of your bot, and allows anyone full access to its account if shared. Be sure to keep it secure, and immediately reset if you think it leaked.

1. The `about` section defines a few traits of the `/about` command. Feel free to change the `description` and the `discord-invite`.

2. You can change `collectible-name` which will replace the word `countryball` in the bot. For instance if you set "rock", the bot will say "A wild rock spawned!" 

3. `bot-name` is used in various places like `/about` or `/balls completion`.

4. The `admin` section configures the `/admin` command. This command is only enabled in specific servers for specific roles.

   1. `guild-ids` is for the servers where you want to enable the `/admin` command. Copy the IDs of the servers you want, and paste them

   2. `root-role-ids` is for the roles IDs which will get **full** access to the `/admin` command, granting the ability to spawn or give balls and control blacklist.

   3. `admin-role-ids` is for the role IDs which will get **partial** access to the `/admin` command. Their access will be limited to blacklist control and seeing shared servers.

!!! abstract "General notice about IDs"
    To obtain an ID, [enable developer mode](https://support.discord.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID-) and right click a server or a role, then select "Copy ID".
    
    If you have just one ID, put it like this (for instance guild IDs)
    ```yaml
    guild-ids:
      - 1049118743101452329
    ```
    
    If you have multiple IDs, they should be placed like this (for instance role IDs here):
    ```yaml
    root-role-ids:
      - 1049119446372986921
      - 1049119786988212296
    ```

There may be other configuration values added over time, look at the comment to understand what they do. If an option is unclear to you, you should leave it to its default value.

<details>
<summary>Here's the <code>config.yml</code> file from Ballsdex if you want to compare and troubleshoot eventual issues:</summary>

```yaml
# yaml-language-server: $schema=json-config-ref.json

# paste the bot token after regenerating it here
discord-token: INSERT_TOKEN_HERE

# prefix for old-style text commands, mostly unused
text-prefix: b.

# define the elements given with the /about command
about:

  # define the beginning of the description of /about
  # the other parts is automatically generated
  description: >
    Collect countryballs on Discord, exchange them and battle with friends!

  # override this if you have a fork
  github-link: https://github.com/laggron42/BallsDex-DiscordBot

  # valid invite for a Discord server
  discord-invite: https://discord.gg/ballsdex  # BallsDex official server

  terms-of-service: https://gist.github.com/laggron42/52ae099c55c6ee1320a260b0a3ecac4e
  privacy-policy: https://gist.github.com/laggron42/1eaa122013120cdfcc6d27f9485fe0bf

# override the name "countryballs" in the bot
collectible-name: countryball

# override the name "BallsDex" in the bot
bot-name: BallsDex

# players group cog command name
# this is /balls by default, but you can change it for /animals or /rocks for example
players-group-cog-name: balls

# enables the /admin command
admin-command:

  # all items here are list of IDs. example on how to write IDs in a list:
  # guild-ids:
  #   - 1049118743101452329
  #   - 1078701108500897923

  # list of guild IDs where /admin should be registered
  guild-ids:
    - 1049118743101452329

  # list of role IDs having full access to /admin
  root-role-ids:
    - 1049119446372986921
    - 1049119786988212296
    - 1095015474846248970

  # list of role IDs having partial access to /admin
  admin-role-ids:
    - 1073775485840003102
    - 1073776116898218036

packages:
  - ballsdex.packages.admin
  - ballsdex.packages.balls
  - ballsdex.packages.config
  - ballsdex.packages.countryballs
  - ballsdex.packages.info
  - ballsdex.packages.players
  - ballsdex.packages.trade

# prometheus metrics collection, leave disabled if you don't know what this is
prometheus:
  enabled: true
  host: "0.0.0.0"
  port: 15260


# manage bot ownership
owners:
  # if enabled and the application is under a team, all team members will be considered as owners
  team-members-are-owners: true

  # a list of IDs that must be considered owners in addition to the application/team owner
  co-owners:
```
</details>

Now we should be ready for the next part.

## 6. Run the bot

To start the bot, simply run `docker compose up`. This will both start the bot and the admin panel, while showing you the live logs. Wait until the line "Ballsdex bot is now ready" shows up, and the bot should be online!

To shut down the bot, use Ctrl+C.

### Detached mode

You will notice that the command above blocks your terminal. You can also run the bot in detached mode with `docker compose up -d` which allows you to keep using the terminal afterwards.

In this mode, you can use `docker compose logs -f` to view the live logs (Ctrl+C to exit). You can also specify containers to filter which logs you want to see, like `docker compose logs -f bot` or `docker compose logs -f admin-panel`.

To shut down the bot in this mode, run `docker compose down`.

## 7. Updating the bot

1. Run `git pull` and wait for the changes to be pulled.
   - If you encounter an error, which may happen when you're editing the source files, run `git reset --hard HEAD` to reset all changes done, then run `git pull` again. Note that it will reset any changes you may have.
2. Fully shut down the bot with `docker compose down` (even if you used Ctrl+C before!)
3. Rebuild the bot with `docker compose build`
4. Start again with `docker compose up` (or `docker compose up -d` in detached)
5. Verify that no error happens while the bot starts!

---

Even if your bot is online, there are no countryballs yet, they need to be added through the administration panel, your tool to control the bot's content.

**The next step of this tutorial is [here](../admin-panel/getting-started.md)**