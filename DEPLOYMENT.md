# Oracle Cloud Free Tier - Deployment Guide

## Step 1: Create Oracle Cloud Account

1. Go to https://www.oracle.com/cloud/free/
2. Click "Start for free"
3. Fill in your details (requires credit card for verification, but won't charge)
4. Select your home region (choose closest to your users)

---

## Step 2: Create a Free VM

1. Go to **Compute → Instances → Create Instance**
2. Configure:
   - **Name**: `footballdex-bot`
   - **Image**: Ubuntu 22.04 (Always Free eligible)
   - **Shape**: VM.Standard.E2.1.Micro (Always Free)
   - **Networking**: Create new VCN or use default
   - **Add SSH Key**: Upload your public key or generate new

3. Click **Create**

---

## Step 3: Configure Firewall

1. Go to **Networking → Virtual Cloud Networks**
2. Select your VCN → Security Lists → Default Security List
3. Add Ingress Rules:

| Port | Protocol | Source | Description |
|------|----------|--------|-------------|
| 22 | TCP | 0.0.0.0/0 | SSH |
| 8000 | TCP | 0.0.0.0/0 | Admin Panel |
| 5432 | TCP | Your IP | PostgreSQL (optional) |

---

## Step 4: Connect to Your VM

```bash
ssh -i your-key.pem ubuntu@YOUR_VM_PUBLIC_IP
```

---

## Step 5: Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to docker group
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Logout and login again for group to take effect
exit
```

Reconnect via SSH.

---

## Step 6: Clone and Configure

```bash
# Clone your repo
git clone https://github.com/Dariusan3/BallsDex-DiscordBot.git
cd BallsDex-DiscordBot

# Create config file
cp config.yaml config.yml

# Edit with your Discord token
nano config.yml
```

Update these in `config.yml`:
- `discord-token`: Your bot token
- `guild-ids`: Your server ID

---

## Step 7: Create .env File

```bash
nano .env
```

Add:
```env
POSTGRES_PASSWORD=your_secure_password_here
```

---

## Step 8: Start Everything

```bash
# Start all services
docker compose up -d

# Check logs
docker compose logs -f
```

---

## Step 9: Access Admin Panel

1. Open in browser: `http://YOUR_VM_PUBLIC_IP:8000`
2. Create admin user:
```bash
docker compose exec admin-panel python3 manage.py createsuperuser
```

---

## Useful Commands

```bash
# View logs
docker compose logs -f bot

# Restart bot
docker compose restart bot

# Stop everything
docker compose down

# Update bot
git pull && docker compose up -d --build
```

---

## Troubleshooting

**Bot not connecting?**
- Check your token in config.yml
- Run `docker compose logs bot`

**Admin panel not loading?**
- Check port 8000 is open in Oracle security list
- Check firewall: `sudo iptables -L`

**Database issues?**
- Check postgres: `docker compose logs postgres-db`

---

## Monthly Cost: $0 🎉

Oracle Always Free tier includes:
- 2 VMs (1GB RAM each)
- 200GB block storage
- 10TB outbound data

This is **permanent** - not a trial!
