# Dokploy & VPS Deployment Guide (interviewv2)

This guide details how to deploy the **Autonomous UKVI Voice Interview System** to a VPS using **Dokploy** and GitHub-driven CI/CD.

---

## Architecture Overview in Dokploy

The repository runs 3 synchronized services managed as a single **Docker Compose Project**:
1. `web_api`: FastAPI application serving the student/admin UI, authentication, REST APIs, and SQLite database.
2. `langgraph_agent`: Autonomous viva examiner worker connected via LiveKit agent dispatch.
3. `livekit`: LiveKit WebRTC server handling real-time audio and data channels.

---

## 1. Dokploy Project Setup (Step-by-Step)

1. **Log in to your Dokploy Dashboard** on your VPS.
2. Click **Create Project** -> Name it `interview-system`.
3. Inside the project, click **Create Service** -> Select **Compose** (Docker Compose).
4. Name the Compose service: `interview-viva`.
5. Under **Provider**, select **GitHub**:
   - Repository: `promit-bhattacharjee/autonomous-interview` (or your repository name).
   - Branch: Choose the target branch (e.g. `main` or `production`).
   - Compose Path: `docker-compose.yml`
6. Check **Auto Deploy**: Dokploy catches changes directly from Git (via Dokploy GitHub App or Git polling), automatically pulling and rebuilding services whenever clean commits land on your designated branch.

---

## 2. Dokploy Environment Variables Configuration

Navigate to the **Environment** tab of the Compose service in Dokploy, and paste the values (referencing [`.env.dokploy.example`](file:///c:/Users/promi/OneDrive/Desktop/interviewv2/.env.dokploy.example)):

```env
# LiveKit Server & Worker Authentication Keys
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=production_livekit_secret_key_ukvi_2026_x91

# Security & Encryption
JWT_SECRET=production-ukvi-jwt-secret-key-32-chars-minimum-entropy
ENCRYPTION_SECRET_KEY=k2t_9uO8zE1M-1A9_N_v7a4jK0tqL6xW9eP8bX2cR0E=

# AI Model Credentials (OpenRouter for DeepSeek V4 Flash thinking)
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_MODEL=deepseek/deepseek-v4-flash-0731
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Google Gemini API Key (STT fallback)
GOOGLE_API_KEY=your-gemini-key-here

# Database
DATABASE_URL=sqlite:////data/interview.db
```

---

## 3. VPS Firewall Configuration (Crucial for WebRTC)

For candidates to establish two-way audio streams, the VPS firewall (UFW and Cloud Security Group) must permit WebRTC traffic:

| Port | Protocol | Purpose | Required Action |
|---|---|---|---|
| **80** | TCP | HTTP Web Traffic / SSL Challenge | Open (Handled by Traefik) |
| **443** | TCP | HTTPS Web Traffic | Open (Handled by Traefik) |
| **8000** | TCP | FastAPI Web UI | Internal (Proxied by Dokploy/Traefik) or Open |
| **7880** | TCP | LiveKit Signaling & Token Validation | Open if not reverse-proxied |
| **7881** | TCP | LiveKit WebRTC TCP Fallback | Open |
| **7882** | **UDP** | **LiveKit WebRTC Media Traffic (Audio Streams)** | **MUST BE OPEN (ufw allow 7882/udp)** |

Run on your VPS terminal:
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 7880/tcp
sudo ufw allow 7881/tcp
sudo ufw allow 7882/udp
sudo ufw reload
```
*(If using AWS, Hetzner, DigitalOcean, or Contabo, also ensure port `7882 UDP` is allowed in the cloud provider's network firewall).*

---

## 4. Domain & SSL Setup in Dokploy

1. In Dokploy, go to the **Domains** tab for the Compose service.
2. Add your primary web domain:
   - Host: `interview.yourdomain.com` (pointing to your VPS IP via DNS A Record)
   - Service: `web_api`
   - Port: `8000`
   - Enable **HTTPS / Let's Encrypt** (Traefik will issue the SSL certificate automatically).
3. (Optional) For LiveKit signaling over SSL:
   - Host: `livekit.yourdomain.com` (DNS A Record)
   - Service: `livekit`
   - Port: `7880`
   - If configured, set `PUBLIC_LIVEKIT_URL=wss://livekit.yourdomain.com` in your Dokploy Environment tab.

---

## 5. Persistent Storage

The SQLite database storing student accounts, question banks, and CAS interview reports is persisted on the host volume `sqlite_data`:
```yaml
volumes:
  sqlite_data:
    driver: local
```
Dokploy will maintain this volume across rebuilds and deployments, ensuring no data loss occurs when code is updated.
