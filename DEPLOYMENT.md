# Deployment & Public Hosting Guide

This guide explains how to take your **College Attendance Management Web App** from localhost to a **public HTTPS URL on the internet** accessible from any phone, laptop, or tablet.

---

## ⚠️ Important Note: Can Antigravity Host Directly?

**No.** Google Antigravity is an AI development workspace and local desktop agent. It does **not** provide cloud web server hosting, cloud DNS, static public IP addresses, or managed servers. 

However, **all required production deployment files have been built and pre-configured for you in this project**, making cloud deployment take only **2–3 minutes**.

---

## Recommended Free Hosting Services

| Provider | Best For | Free Tier | Custom Domain / HTTPS | Setup Time |
| :--- | :--- | :--- | :--- | :--- |
| **Render.com** *(Top Pick)* | Flask + Gunicorn | ✅ Free Web Service | ✅ Automatic `*.onrender.com` HTTPS | ~3 mins |
| **Railway.app** | Docker / GitHub | ✅ Free starter credit | ✅ Automatic `*.up.railway.app` HTTPS | ~2 mins |
| **PythonAnywhere** | Pure Python/WSGI | ✅ Free subdomain | ✅ Automatic `*.pythonanywhere.com` HTTPS | ~5 mins |

---

## 🚀 Option 1: Deploy to Render.com (Recommended)

Render is the simplest and most reliable host for Flask applications. It provides free automatic SSL (`https://`), auto-deploys from GitHub, and handles Gunicorn out of the box.

### Step 1: Upload Project to GitHub
1. Go to [github.com](https://github.com) and create a new repository (e.g., `college-attendance-app`).
2. Upload the files in this folder to your repository, or push via Git:
   ```bash
   git init
   git add .
   git commit -m "Production college attendance app"
   git branch -M main
   git remote add origin https://github.com/<YOUR_USERNAME>/college-attendance-app.git
   git push -u origin main
   ```

### Step 2: Create Free Web Service on Render
1. Visit [render.com](https://render.com) and sign in (you can use your GitHub account).
2. Click **New +** > **Web Service**.
3. Select your repository `college-attendance-app`.
4. Render will automatically detect the settings from `render.yaml` and `Procfile`. Verify:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4`
   - **Instance Type**: `Free`
5. Click **Create Web Service**.

### Step 3: Access Your Public HTTPS URL
- In ~2 minutes, Render will build and deploy your app.
- Render assigns a public HTTPS URL:
  ```
  https://college-attendance-app-xxxx.onrender.com
  ```
- Open this URL on your phone, laptop, or share it with classmates!

---

## ⚡ Option 2: Deploy to Railway.app

1. Go to [railway.app](https://railway.app) and sign in with GitHub.
2. Click **New Project** > **Deploy from GitHub repo**.
3. Select `college-attendance-app`.
4. Railway will automatically build using the included `Dockerfile` or `Procfile`.
5. Under **Settings** > **Networking**, click **Generate Domain**.
6. You will instantly receive a public HTTPS URL (e.g., `https://college-attendance-app.up.railway.app`).

---

## 📲 Instant Testing on Your Phone (Same Wi-Fi Network)

If your computer and mobile phone are connected to the same Wi-Fi router, you can test on your phone **right now** without any cloud setup:

1. Your current local network IP address is:
   ```
   http://192.168.1.69:5000
   ```
2. Open your phone's browser (Safari/Chrome) and type `http://192.168.1.69:5000`.
3. You can log in, create timetable periods, and mark attendance directly from your phone!
*(Make sure Windows Firewall allows incoming connections on port 5000 if prompted).*

---

## 🔒 Production Security & Environment Variables

When deploying to Render or Railway, you can configure the following environment variables in their dashboard:

| Variable | Recommended Value | Purpose |
| :--- | :--- | :--- |
| `SECRET_KEY` | *(Random 32-char hex string)* | Signs session tokens securely |
| `FLASK_DEBUG` | `False` | Disables Flask debug mode in production |
| `DATABASE_PATH` | `/data/attendance.db` *(if using persistent disk)* | Custom path for SQLite database |
