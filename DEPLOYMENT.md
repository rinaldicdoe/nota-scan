# 🔒 Panduan Deployment Aman

## ⚠️ PENTING: Keamanan API Key & Credentials

**JANGAN PERNAH** commit file berikut ke Git/GitHub:
- ❌ `.env` - berisi API key
- ❌ `credentials.json` - berisi Google credentials
- ❌ `.streamlit/secrets.toml` - berisi secrets

File-file ini sudah di-exclude di `.gitignore`.

---

## 🚀 Opsi Deployment

### Opsi 1: Streamlit Cloud (Gratis & Mudah) ⭐ RECOMMENDED

#### Setup:
1. **Push code ke GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/username/scan-nota.git
   git push -u origin main
   ```

2. **Deploy di Streamlit Cloud**
   - Buka https://share.streamlit.io/
   - Login dengan GitHub
   - Klik "New app"
   - Pilih repository Anda
   - Main file: `app.py`

3. **Setup Secrets di Streamlit Cloud**
   - Setelah deploy, klik "Settings" > "Secrets"
   - Copy isi dari `.streamlit/secrets.toml.example`
   - Ganti dengan API key dan credentials Anda yang sebenarnya
   - Paste ke Secrets editor
   - Klik "Save"

4. **Format Secrets (TOML format)**
   ```toml
   OPENAI_API_KEY = "sk-PpZ8ebBEJ-03Chpt3w-E8Q"
   OPENAI_BASE_URL = "https://ai.sumopod.com"
   SHEET_NAME = "Data Nota"
   WORKSHEET_NAME = "Sheet1"
   
   [GOOGLE_CREDENTIALS]
   type = "service_account"
   project_id = "your-actual-project-id"
   private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
   client_email = "your-service-account@project-id.iam.gserviceaccount.com"
   # ... sisanya dari credentials.json
   ```

5. **Reboot app** setelah save secrets

✅ **Keuntungan:**
- Gratis untuk public apps
- Auto-deploy saat push ke GitHub
- HTTPS built-in
- Mudah manage secrets

---

### Opsi 2: Heroku

#### Setup:
1. **Install Heroku CLI**
   ```bash
   brew tap heroku/brew && brew install heroku
   ```

2. **Buat `setup.sh`**
   ```bash
   mkdir -p ~/.streamlit/
   echo "\
   [server]\n\
   headless = true\n\
   port = $PORT\n\
   enableCORS = false\n\
   \n\
   " > ~/.streamlit/config.toml
   ```

3. **Buat `Procfile`**
   ```
   web: sh setup.sh && streamlit run app.py
   ```

4. **Deploy**
   ```bash
   heroku login
   heroku create scan-nota-app
   
   # Set environment variables
   heroku config:set OPENAI_API_KEY="sk-PpZ8ebBEJ-03Chpt3w-E8Q"
   heroku config:set OPENAI_BASE_URL="https://ai.sumopod.com"
   heroku config:set SHEET_NAME="Data Nota"
   heroku config:set WORKSHEET_NAME="Sheet1"
   
   # Push
   git push heroku main
   ```

5. **Upload credentials.json**
   - Encode ke base64:
     ```bash
     base64 credentials.json | tr -d '\n' > credentials_base64.txt
     ```
   - Set sebagai env var:
     ```bash
     heroku config:set GOOGLE_CREDENTIALS_BASE64="$(cat credentials_base64.txt)"
     ```
   - Update `app.py` untuk decode dari env var

---

### Opsi 3: Docker + Cloud Run / Railway

#### Dockerfile:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

#### Deploy ke Google Cloud Run:
```bash
gcloud run deploy scan-nota \
  --source . \
  --platform managed \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --set-env-vars OPENAI_API_KEY=sk-xxx,OPENAI_BASE_URL=https://ai.sumopod.com
```

---

### Opsi 4: VPS (DigitalOcean, AWS EC2, dll)

#### Setup di Server:
```bash
# Install dependencies
sudo apt update
sudo apt install python3-pip poppler-utils

# Clone repo
git clone https://github.com/username/scan-nota.git
cd scan-nota

# Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Setup .env file
nano .env
# Isi dengan API key Anda

# Upload credentials.json
scp credentials.json user@server:/path/to/scan-nota/

# Run dengan systemd atau PM2
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

#### Setup Nginx reverse proxy:
```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

---

## 🔐 Best Practices Keamanan

### 1. Environment Variables
✅ **LAKUKAN:**
- Simpan API key di environment variables
- Gunakan `.env` file untuk local development
- Tambahkan `.env` ke `.gitignore`

❌ **JANGAN:**
- Hardcode API key di source code
- Commit `.env` atau `credentials.json` ke Git
- Share API key di public

### 2. Google Credentials
✅ **LAKUKAN:**
- Simpan `credentials.json` di server secara aman
- Atau encode ke base64 dan simpan sebagai env var
- Restrict permissions ke service account

### 3. Git Repository
```bash
# Cek apakah ada file sensitif sebelum commit
git status

# Pastikan .gitignore sudah benar
cat .gitignore

# Jangan pernah commit ini:
# - .env
# - credentials.json
# - .streamlit/secrets.toml
```

---

## 📊 Perbandingan Platform

| Platform | Gratis? | Kemudahan | HTTPS | Auto-deploy |
|----------|---------|-----------|-------|-------------|
| **Streamlit Cloud** | ✅ | ⭐⭐⭐⭐⭐ | ✅ | ✅ |
| Heroku | ⚠️ Limited | ⭐⭐⭐⭐ | ✅ | ✅ |
| Cloud Run | ⚠️ Pay-as-go | ⭐⭐⭐ | ✅ | ⚠️ |
| Railway | ⚠️ Limited | ⭐⭐⭐⭐ | ✅ | ✅ |
| VPS | ❌ | ⭐⭐ | Manual | ❌ |

---

## 🎯 Rekomendasi

**Untuk Anda:** Gunakan **Streamlit Cloud** karena:
1. ✅ Gratis
2. ✅ Paling mudah setup
3. ✅ Built-in secrets management
4. ✅ Auto-deploy dari GitHub
5. ✅ HTTPS otomatis
6. ✅ Tidak perlu manage server

---

## 🆘 Troubleshooting

### "API Key not found"
- Pastikan secrets sudah disave di Streamlit Cloud
- Format harus TOML (bukan JSON)
- Reboot app setelah update secrets

### "Credentials error"
- Pastikan format `[GOOGLE_CREDENTIALS]` benar
- Private key harus include `\n` untuk newlines
- Pastikan semua field dari credentials.json ada

### "ModuleNotFoundError"
- Pastikan `requirements.txt` ter-push ke GitHub
- Streamlit Cloud akan auto-install dependencies
