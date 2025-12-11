# 🧾 AI Nota Scanner

Aplikasi web untuk mengkonversi foto atau PDF nota menjadi data terstruktur menggunakan AI Vision (OpenAI GPT-4o), lalu menyimpannya ke Google Sheets.

## ✨ Fitur Utama

- 📸 **Upload Foto/PDF Nota** - Support format JPG, PNG, PDF
- 🤖 **AI Vision OCR** - Menggunakan OpenAI GPT-4o untuk ekstraksi data yang sangat akurat
- 🎯 **Confidence Indicator** - Visual warning (⚠️ ❗) untuk field yang AI ragu, perlu review manual
- 🔧 **Validasi Otomatis** - Deteksi dan koreksi otomatis untuk:
  - Hyper-efficiency: Harga "20" yang sebenarnya "20.000"
  - Kuantitas abstrak: "1/2" atau "0.5" untuk setengah
  - Balance check: Memastikan qty × harga_satuan = total_harga
- ✏️ **Edit Preview** - Review dan edit data sebelum disimpan
- 💾 **Auto Save ke Google Sheets** - Otomatis simpan ke spreadsheet
- 🎯 **Smart Extraction** - Hanya ambil nama barang, qty, dan harga (abaikan header/footer)

## 🛠 Stack Teknologi

- **Python 3.8+** - Bahasa pemrograman
- **Streamlit** - Framework web app
- **OpenAI GPT-4o Vision** - AI untuk OCR dan ekstraksi data
- **Google Sheets API** - Penyimpanan data
- **pdf2image** - Konversi PDF ke gambar
- **pandas** - Manipulasi data

## 📋 Prasyarat

### 1. Install Poppler (untuk konversi PDF)

**macOS:**

```bash
brew install poppler
```

**Ubuntu/Debian:**

```bash
sudo apt-get install poppler-utils
```

**Windows:**

- Download dari: http://blog.alivate.com.au/poppler-windows/
- Extract dan tambahkan ke PATH

### 2. OpenAI API Key

1. Daftar/login ke https://platform.openai.com/
2. Buat API Key di https://platform.openai.com/api-keys
3. Copy API key Anda

### 3. Google Cloud Service Account

1. Buka https://console.cloud.google.com/
2. Buat project baru atau pilih yang sudah ada
3. Enable **Google Sheets API** dan **Google Drive API**
4. Buat Service Account:
   - Pergi ke **IAM & Admin** > **Service Accounts**
   - Klik **Create Service Account**
   - Beri nama (misal: `nota-scanner-bot`)
   - Klik **Create and Continue**
   - Skip role assignment (klik Continue)
   - Klik **Done**
5. Generate Key:
   - Klik service account yang baru dibuat
   - Tab **Keys** > **Add Key** > **Create New Key**
   - Pilih format **JSON**
   - Download file JSON (ini akan jadi `credentials.json`)

### 4. Setup Google Sheets

1. Buka Google Sheets: https://sheets.google.com/
2. Buat spreadsheet baru dengan nama: **Data Nota**
3. Share spreadsheet dengan email service account:
   - Klik tombol **Share**
   - Paste email service account (ada di file credentials.json, field `client_email`)
   - Beri akses **Editor**
   - Klik **Send**

## 🚀 Instalasi

### 1. Clone/Download Project

```bash
cd ~/Documents
mkdir scan-nota
cd scan-nota
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Setup Konfigurasi

#### Opsi A: Menggunakan File .env (Recommended)

```bash
# Copy template
cp .env.example .env

# Edit file .env
nano .env  # atau gunakan text editor lain
```

Isi file `.env`:

```env
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SHEET_NAME=Data Nota
WORKSHEET_NAME=Sheet1
```

#### Opsi B: Edit Langsung di app.py

Edit baris berikut di `app.py`:

```python
OPENAI_API_KEY = "sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
SHEET_NAME = "Data Nota"
WORKSHEET_NAME = "Sheet1"
```

### 4. Upload Credentials Google

Copy file JSON credentials yang sudah didownload ke folder project dengan nama `credentials.json`:

```bash
cp ~/Downloads/service-account-key-xxxxx.json credentials.json
```

## ▶️ Menjalankan Aplikasi

```bash
streamlit run app.py
```

Aplikasi akan terbuka otomatis di browser di `http://localhost:8501`

## 📖 Cara Penggunaan

1. **Upload Nota**

   - Klik tombol upload di sidebar
   - Pilih file foto (JPG/PNG) atau PDF nota

2. **Scan dengan AI**

   - Klik tombol "🔍 Scan Nota dengan AI"
   - Tunggu beberapa detik untuk proses ekstraksi

3. **Review & Edit**

   - Cek tabel hasil scan
   - Klik cell untuk mengedit jika ada kesalahan
   - Tambah/hapus baris jika perlu

4. **Simpan ke Google Sheets**
   - Klik tombol "💾 Simpan ke Google Sheet"
   - Data akan tersimpan otomatis dengan timestamp

## 📁 Struktur Project

```
scan-nota/
├── app.py                    # Main application
├── requirements.txt          # Python dependencies
├── credentials.json          # Google Service Account (jangan commit!)
├── .env                      # Environment variables (jangan commit!)
├── .env.example             # Template environment variables
├── .gitignore               # Git ignore file
└── README.md                # Dokumentasi ini
```

## 🔒 Keamanan

**PENTING:** Jangan commit file berikut ke Git:

- `credentials.json` - Berisi credentials Google Cloud
- `.env` - Berisi API key OpenAI

File-file ini sudah di-exclude di `.gitignore`.

## 🐛 Troubleshooting

### Error: "Poppler not found"

```bash
# macOS
brew install poppler

# Ubuntu
sudo apt-get install poppler-utils
```

### Error: "Google Sheet tidak ditemukan"

- Pastikan nama sheet sesuai (default: "Data Nota")
- Pastikan service account sudah di-invite ke sheet sebagai Editor
- Check email service account di file credentials.json

### Error: "OpenAI API Error"

- Check API key valid dan masih aktif
- Pastikan credit OpenAI masih tersedia
- Check koneksi internet

### Error: "Permission denied" untuk Google Sheets

- Pastikan service account sudah di-share dengan akses Editor
- Check email service account di credentials.json
- Pastikan Google Sheets API sudah enabled

## 💡 Tips Penggunaan

1. **Kualitas Foto:**

   - Gunakan foto dengan pencahayaan yang baik
   - Pastikan teks jelas dan tidak blur
   - Ambil foto dari atas (tegak lurus)

2. **Format Nota:**

   - Aplikasi paling baik untuk nota dengan format tabel/list
   - Nota tulisan tangan mungkin kurang akurat

3. **Efisiensi Biaya:**
   - Model GPT-4o Vision memerlukan biaya per request
   - Review hasil sebelum scan ulang
   - Gunakan foto/PDF berkualitas untuk hasil optimal

## 🎯 Confidence Indicator

AI akan memberikan **tingkat kepercayaan (confidence score)** untuk setiap field yang diekstrak. Field dengan confidence rendah akan ditandai dengan emoji visual:

### Indikator Visual

| Emoji   | Confidence | Keterangan       | Tindakan           |
| ------- | ---------- | ---------------- | ------------------ |
| ❗      | < 70%      | **Perlu Review** | Wajib dicek manual |
| ⚠️      | 70-79%     | **Cek Ulang**    | Disarankan review  |
| (tanpa) | ≥ 80%      | **Data Akurat**  | Aman digunakan     |

### Kapan AI Memberikan Confidence Rendah?

AI akan memberikan confidence < 80% jika:

- Teks blur atau tidak jelas
- Tulisan tangan yang sulit dibaca
- Angka yang ambigu atau terpotong
- Harus melakukan asumsi/tebakan
- Format tidak standar

### Contoh Tampilan

```
📊 Hasil Ekstraksi Data

Legend:
❗ = Perlu Review
⚠️ = Cek Ulang

| Nama Barang           | Qty | Harga Satuan | Total Harga |
|-----------------------|-----|--------------|-------------|
| ❗ Beras Premium      | 2   | 15000        | 30000       |
| ⚠️ Minyak Goreng     | 1   | 25000        | 25000       |
| Gula Pasir            | 0.5 | 14000        | 7000        |
```

**Penjelasan:**

- **❗ Beras Premium**: Nama barang tidak jelas di foto, perlu dicek manual
- **⚠️ Minyak Goreng**: Tulisan agak blur, disarankan review
- **Gula Pasir**: Semua field jelas, tidak perlu review

### Notifikasi

Setelah scan, sistem akan memberitahu jika ada field yang perlu review:

```
⚠️ 3 field memiliki confidence rendah. Ditandai dengan ⚠️ atau ❗. Silakan review!
```

## 🔧 Fitur Validasi Otomatis

Sistem dilengkapi dengan validasi dan koreksi otomatis untuk menangani kasus-kasus khusus dalam pembacaan nota:

### 1. Hyper-efficiency (Penulisan Harga Singkat)

Kasir sering menulis harga dengan cara singkat:

- "20" untuk maksud "20.000"
- "20k" untuk maksud "20.000"

**Contoh:**

```
Input dari AI:
- Beras: qty=2, harga_satuan=15, total_harga=30000

Sistem mendeteksi ketidaksesuaian dan mengoreksi:
✅ 'Beras': Harga satuan dikoreksi 15 → 15,000 (hyper-efficiency)

Output:
- Beras: qty=2, harga_satuan=15000, total_harga=30000
```

### 2. Kuantitas Abstrak

Mendukung penulisan kuantitas dalam bentuk pecahan:

- "1/2" untuk setengah kilo → 0.5
- "0.5" untuk setengah
- Garis miring "/" → 0.5

**Contoh:**

```
- Gula Pasir: qty=0.5, harga_satuan=14000, total_harga=7000
```

### 3. Balance Check

Memastikan perhitungan benar: `qty × harga_satuan = total_harga`

**Contoh:**

```
Input dari AI:
- Minyak: qty=3, harga_satuan=10000, total_harga=33000

Sistem mendeteksi ketidaksesuaian (3 × 10000 ≠ 33000):
⚖️ 'Minyak': Balance dikoreksi - Harga satuan 10,000 → 11,000 (qty=3, total=33,000)

Output:
- Minyak: qty=3, harga_satuan=11000, total_harga=33000
```

### Log Koreksi

Setelah scan, sistem akan menampilkan log koreksi yang dilakukan:

```
🔧 Koreksi Otomatis (3 perubahan)
✅ 'Beras': Harga satuan dikoreksi 15 → 15,000 (hyper-efficiency)
⚖️ 'Gula': Balance dikoreksi - Harga satuan 20,000 → 24,000 (qty=0.5, total=12,000)
✅ 'Minyak': Harga satuan dikoreksi 18 → 18,000 (hyper-efficiency)
```

Untuk detail lengkap, lihat [VALIDATION.md](VALIDATION.md)

## 📊 Output Data

Data yang disimpan ke Google Sheets:

| timestamp           | nama_barang | qty | harga_satuan | total_harga |
| ------------------- | ----------- | --- | ------------ | ----------- |
| 2024-01-15 10:30:00 | Kopi Susu   | 2   | 15000        | 30000       |
| 2024-01-15 10:30:00 | Roti Bakar  | 1   | 12000        | 12000       |

## 🔄 Update Dependencies

Untuk update semua dependencies ke versi terbaru:

```bash
pip install --upgrade -r requirements.txt
```

## 🤝 Kontribusi

Silakan buat issue atau pull request untuk perbaikan dan fitur baru!

## 📝 License

MIT License - Silakan gunakan untuk keperluan pribadi atau komersial.

## 📧 Support

Jika ada pertanyaan atau masalah, buat issue di repository ini.

---

**Dibuat dengan ❤️ menggunakan Python + Streamlit + OpenAI GPT-4o**
