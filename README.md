# 🩺 Container Doctor (AI DevOps Agent)

An AI-powered container monitoring and self-healing system built using Docker, Python, and Google Gemini API.

## 🚀 Features

- 🔍 Real-time container log monitoring
- 🤖 AI-based root cause analysis (Gemini)
- ⚠️ Severity classification (low/medium/high)
- 🔧 Automated container restart (safe cases)
- 📢 Slack notifications
- 📊 Health & history endpoints

## 🏗️ Architecture

Containers → Logs → Container Doctor → Gemini AI → Fix / Alert

## ⚙️ Setup

### 1. Clone repo
```bash
git clone https://github.com/YOUR_USERNAME/container-doctor.git
cd container-doctor

### 2. Create .env
GEMINI_API_KEY=your_key
TARGET_CONTAINERS=web,api,db
CHECK_INTERVAL=10
LOG_LINES=50
AUTO_FIX=true
SLACK_WEBHOOK_URL=
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_pass
POSTGRES_DB=your_db

### 3. Run 
docker compose up -d --build


### 4. test
curl http://localhost:5000/crash
docker logs -f container_doctor
