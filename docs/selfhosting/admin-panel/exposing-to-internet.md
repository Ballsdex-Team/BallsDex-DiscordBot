If you want to leverage your experience and be able to access your admin panel from anywhere and share it with your staff, you can host it on a server and expose it to the internet! It's not an easy process but I will try to guide you there.

## 1. Requirements

### Pre-requirements

#### Ballsdex hosted on an online Linux server

It is **extremely** important that you do not host Ballsdex or the website on your own personal network. This would require you to open your firewall and expose your entire family to tons of dangers. **DO NOT DO THIS** and look for a provider, there are even free options.

I recommend checking [this page](https://docs.discord.red/en/stable/host-list.html) for VPS and server recommendations.

The reason Linux is a requirement in this tutorial is simply because I don't know how this works on Windows or macOS, I cannot teach that. Besides, it would be weird to pay an additional sum for a paid OS when Linux is the recommended OS.

#### Your own domain name

You must have a domain name to hide your IP. This is pretty cheap honestly, I recommend you to use [Namecheap](https://www.namecheap.com/) for cheap domain names, it's what I use myself.

Once you got this, you should also use [Cloudflare](https://www.cloudflare.com/) as a DNS and proxy provider, it's free, faster than the default DNS, and comes with many good features. Your server's IP will be hidden thanks to that.

#### Docker-managed Ballsdex

In this tutorial, we will only cover Docker installations of Ballsdex.

If you are not using Docker, you will need to configure nginx yourself to serve the static files.

----

!!! caution
    It is very important that you follow these requirements, **they have security implications**.  
    Failing to follow these will result in being exposed to a lot of risks and vulnerabilities if you don't exactly know what you're doing and how it works.

### Routing your domain name

On Cloudflare, create a new configuration for your domain `example.com`. It will ask you to replace nameservers with its own on Namecheap's side. Do this and wait for the changes to take effect (can take a while).

Once Cloudflare is ready, go to the DNS page, create an `A` record and redirect it to your server's IP. If you don't know your server's IP, you can run `curl http://ipinfo.io/ip`. Be sure to tick "Proxy" on.

#### Using HTTPS

To have secure connections, it is highly recommended to have HTTPS connections. Luckily, Cloudflare can handle that for us.

1. In Cloudflare's settings, open **SSL/TLS Overview** in the sidebar
2. Next to "SSL/TLS encryption", click **Configure**
3. Choose "Automatic". It should have at least "Flexible" mode on.

If you want to have full end-to-end encryption, you can have a strict policy and generate your own certificates using `certbot`. [Tutorial](https://www.digitalocean.com/community/tutorials/how-to-secure-nginx-with-let-s-encrypt-on-ubuntu-22-04)

!!! warning
    Using unsecure HTTP to access your admin panel is dangerous. All traffic between you and the server is readable by anyone in-between, including passwords.

### Program requirements

We are going to use the `pwgen` to generate secret keys.On Debian/Ubuntu, run this:
```bash
sudo apt update
sudo apt install pwgen
```

If you are using a different distribution, look up your package manager to see how to install those dependencies.

## 2. Setting up a firewall

Before opening yourself to the internet, ensure that your OS is configured to only allow what we need.

Distributions have different firewall programs, but the most common one is `ufw` (preinstalled on Ubuntu). Let's configure it together.

1. Disallow all incoming connections: `sudo ufw default deny incoming`
2. Allow all outgoing connections: `sudo ufw default allow outgoing`
3. Allow SSH connections: `sudo ufw allow OpenSSH`
4. Allow HTTP and HTTPS connections: `sudo ufw allow 'Nginx Full'`
5. Enable ufw: `sudo ufw enable`

If you do not have `ufw` on your system, look up what program is recommended for your distribution and allow ports 22 and 80.

## 3. Configuring the Ballsdex admin panel

We're slowly getting there! Now we just need to configure the last few bits on Ballsdex's side.

### Configure the production settings

In production, we need different settings for Django. An example `production.py` file is provided, which we will copy and fill. Open a shell and type the following commands:

1. `cd config`
2. `cp production.example.py production.py`
3. Generate a random string of characters with `pwgen -n 64 1` and copy that
4. `nano production.py` (or your preferred editor)
5. Find the line that says `SECRET_KEY = None` and replace it with `SECRET_KEY = "paste your random string here"`
6. Look down for the `ALLOWED_HOSTS` section and replace `localhost` by your domain
7. Exit and save with Ctrl+x, `yes` and enter.

This `production.py` file should remain secret and never be pushed. It will be ignored by git.

!!! warning
    Keep your `SECRET_KEY` secret. Running Django with a known `SECRET_KEY` defeats many of Django’s security protections, and can lead to privilege escalation and remote code execution vulnerabilities.  
    <https://docs.djangoproject.com/en/5.1/ref/settings/#secret-key>

!!! tip
    Feel free to edit the `production.py` file to extend the configuration and add more settings, such as extensions or custom admin themes.  
    Future updates will change settings in `base.py` and `production_base.py` and automatically apply to your configuration.

### Telling Django about your settings

To make use of that `production.py` file, you need to tell Django via the `DJANGO_SETTINGS_MODULE` environment variable.

You will find in `docker-compose.yml` there is already a commented environment variable, simply uncomment that line. If you're not using docker compose, simply run `export DJANGO_SETTINGS_MODULE=config.production` before running the server.

----

At this point, restart your admin panel and you should now be able to access it at your domain name, in https, from anywhere!

## Next steps

Now that your admin panel is online, there are some additional settings that may interest you.

### Discord OAuth2

If you followed the first guide, you may have configured Discord OAuth2 to login with Discord and not create accounts. **This now applies to your staff too!** Here's how the Discord pipeline works:

- Does the user have Two-factor authentication enabled?
  - If not, login is immediately denied.
- Is the user ID in the `co-owners` section of `config.yml`?
  - If yes, the user is granted the **superuser** status.
- Is the user ID the owner of the Discord application?
  - If yes, the user is granted the **superuser** status.
- Is `team-members-are-owners` set to `true` in `config.yml`, and is the user ID part of the Discord developer team that owns the application (regardless of its role)?
  - If yes, the user is granted the **superuser** status.
- Does the user possess one of the roles defined in `root-role-ids` in `config.yml`?
  - If yes, the user is granted the **staff** status and is assigned the **Admin group** (detailed below).
- Does the user possess one of the roles defined in `admin-role-ids` in `config.yml`?
  - If yes, the user is granted the **staff** status and is assigned the **Staff group** (detailed below).

If you have configured a Discord webhook, you will be notified for each new user that registers successfully on your admin panel. It is highly recommended to have this setup!

!!! danger
    Here's the very important part, **staff status is not automatically unassigned if you demote a user in Discord!!**

    When demoting someone (admin/root role removed, removed from the Developer team or the `co-owners` list), you must also go to the admin panel, "Users", edit the user (if they registered on the panel) and untick the "Is Active" box.  
    You do not need to untick "Is staff", "Is superuser" or remove permissions groups. Unticking "Is Active" completely disables logging in and invalidates all sessions. If you want to re-enable the user, simply tick this box back.

    It is important that you do not delete the user, or you will be losing all audit logs!

#### Disabling Discord OAuth2

If you prefer creating admin accounts yourself and not automatically give access to all your staff, you can disable the "Login with Discord" button by adding the following lines to your `production.py` file:

```py
AUTHENTICATION_BACKENDS = [
    # "social_core.backends.discord.DiscordOAuth2",
    "django.contrib.auth.backends.ModelBackend",
]
```

Simply uncomment the line if you want to re-enable this.

### Creating new accounts

Whether you have Discord OAuth2 or not, you can always choose to create manual admin accounts with a login and a password.

For that, open the admin panel and click the "+ Add" button next to "Users". Choose a login and a password. Once created, you can then edit the user's permissions.  
It is recommended that you ask users to reset their password as soon as they login for the first time. They can do so by clicking the button on the top right of the admin panel.

!!! warning
    If you need to delete a user, **do not actually delete it as you will be losing all audit logs!** Instead, untick the "Is active" checkbox, that will prevent them from logging in and invalidate all existing sessions.  
    To re-enable access, simply tick that box again. The previous permissions will apply.

#### Creating a superuser account from the command line

If you need to create a new superuser account without accessing the admin panel (for instance, the first admin account), you can use the following command and follow the prompts.

- With docker: `docker compose exec admin-panel python3 -m django createsuperuser`
- Without docker: `DJANGO_SETTINGS_MODULE=admin_panel.settings python3 -m django createsuperuser`

#### Disabling password authentication

If you want to exclusively rely on Discord OAuth2 for authentication, you can disable password-based accounts by adding the following lines to your `production.py` file:

```py
AUTHENTICATION_BACKENDS = [
    "social_core.backends.discord.DiscordOAuth2",
    # "django.contrib.auth.backends.ModelBackend",
]
```

Simply uncomment the line if you want to re-enable this.

### Handling permissions

Django has an extensive permission system described [here](https://docs.djangoproject.com/en/5.1/topics/auth/default/#permissions-and-authorization).

Put simply, each model (Ball, BallInstance, Regime, Player, ...) has 4 permissions by default: view, change, add, delete. Users with the "superuser" status bypasses all permissions and has access to everything.

You can assign permissions to individual users by editing their user object, but you can also use permission groups.

#### Using groups

Under the "Authorization & Authentication" section, you will find a "Group" section, allowing you to create named groups with a set of permissions.

If you have staff members logging in, you will get two groups created automatically, with the corresponding permissions assigned.

<details>
<summary>Click to unroll the default groups and permissions</summary>
<table><thead>
  <tr>
    <th></th>
    <th>Permission</th>
    <th>Staff</th>
    <th>Admin</th>
  </tr></thead>
<tbody>
  <tr>
    <td rowspan="4">Ball</td>
    <td>View</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Change</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Add</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Delete</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td rowspan="4">Regime</td>
    <td>View</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Change</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Add</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Delete</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td rowspan="4">Economy</td>
    <td>View</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Change</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Add</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Delete</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td rowspan="4">Special</td>
    <td>View</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Change</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Add</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Delete</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td rowspan="4">BallInstance</td>
    <td>View</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Change</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Add</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Delete</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td rowspan="4">BlacklistedID</td>
    <td>View</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Change</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Add</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Delete</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td rowspan="4">BlacklistedGuild</td>
    <td>View</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Change</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Add</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Delete</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td rowspan="4">BlacklistHistory</td>
    <td>View</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Change</td>
    <td>❌</td>
    <td>❌</td>
  </tr>
  <tr>
    <td>Add</td>
    <td>❌</td>
    <td>❌</td>
  </tr>
  <tr>
    <td>Delete</td>
    <td>❌</td>
    <td>❌</td>
  </tr>
  <tr>
    <td rowspan="4">Block</td>
    <td>View</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Change</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Add</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Delete</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td rowspan="4">Friendship</td>
    <td>View</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Change</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Add</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Delete</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td rowspan="4">GuildConfig</td>
    <td>View</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Change</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Add</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Delete</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td rowspan="4">Player</td>
    <td>View</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Change</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Add</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Delete</td>
    <td>❌</td>
    <td>✅</td>
  </tr>
  <tr>
    <td rowspan="4">Trade</td>
    <td>View</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Change</td>
    <td>❌</td>
    <td>❌</td>
  </tr>
  <tr>
    <td>Add</td>
    <td>❌</td>
    <td>❌</td>
  </tr>
  <tr>
    <td>Delete</td>
    <td>❌</td>
    <td>❌</td>
  </tr>
  <tr>
    <td rowspan="4">TradeObject</td>
    <td>View</td>
    <td>✅</td>
    <td>✅</td>
  </tr>
  <tr>
    <td>Change</td>
    <td>❌</td>
    <td>❌</td>
  </tr>
  <tr>
    <td>Add</td>
    <td>❌</td>
    <td>❌</td>
  </tr>
  <tr>
    <td>Delete</td>
    <td>❌</td>
    <td>❌</td>
  </tr>
</tbody></table></details>

!!! tip
    You are free to edit those permissions after they were created.