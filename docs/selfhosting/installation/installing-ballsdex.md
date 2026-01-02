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
2. Run `docker compose run --rm admin-panel python3 -m django createsuperuser` to create an admin user
   for the admin panel. The email does not actually matter.

    !!! note
        Your password will not show while typing, that's normal, just press enter when you're done.

3. Run `docker compose up -d proxy` to boot up the admin panel

## 5. Configure the bot

Open <http://localhost:8000> in your browser, this will take you to the
admin panel login page. Login using the credentials you have set before.

!!! tip
    If you forgot your credentials, run
    `docker compose run --rm admin-panel python3 -m django changepassword <username>`

1. Go back to the Discord developer portal and click "Reset Token" to obtain a new one.
   Copy and paste it in the "Discord token" section.

    !!! danger
        **Do not share your token!** It is the password of your bot, and allows anyone full access
        to its account if shared. Be sure to keep it secure, and immediately reset if you think it leaked.

2. You can change "Collectible name" which will replace the word "countryball" in the bot. For instance if you set "rock", the bot will say "A wild rock spawned!" 

3. "Bot name" is used in various places like `/about` or `/balls completion`.

4. The "/about" section defines a few traits of the `/about` command. Feel free to change the description and set a Discord invite.
   You must also write your terms of service and a privacy policy and place the link to them (can be a Google Docs).

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