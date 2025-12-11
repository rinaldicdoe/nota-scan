import streamlit as st
import pandas as pd
import json
import base64
import gspread
import os
from oauth2client.service_account import ServiceAccountCredentials
from openai import OpenAI
from pdf2image import convert_from_bytes
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables dari .env file (untuk local development)
load_dotenv()

# ==========================================
# 1. KONFIGURASI & SETUP
# ==========================================

# KEAMANAN: Gunakan Streamlit Secrets atau Environment Variables
# Jangan hardcode API key di sini!

# Coba ambil dari Streamlit secrets dulu (untuk deployment), 
# kalau tidak ada, ambil dari environment variable
try:
    # Untuk Streamlit Cloud deployment
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    OPENAI_BASE_URL = st.secrets.get("OPENAI_BASE_URL", "https://ai.sumopod.com")
    SHEET_NAME = st.secrets.get("SHEET_NAME", "Data Nota")
    WORKSHEET_NAME = st.secrets.get("WORKSHEET_NAME", "Sheet1")
    
    # Credentials Google bisa dari secrets atau file
    if "GOOGLE_CREDENTIALS" in st.secrets:
        # Jika credentials disimpan sebagai JSON string di secrets
        import tempfile
        credentials_dict = dict(st.secrets["GOOGLE_CREDENTIALS"])
        GOOGLE_CREDENTIALS_FILE = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(credentials_dict, GOOGLE_CREDENTIALS_FILE)
        GOOGLE_CREDENTIALS_FILE.close()
        GOOGLE_CREDENTIALS_FILE = GOOGLE_CREDENTIALS_FILE.name
    else:
        GOOGLE_CREDENTIALS_FILE = "credentials.json"
        
except (FileNotFoundError, KeyError, AttributeError):
    # Fallback ke environment variables untuk local development
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://ai.sumopod.com")
    SHEET_NAME = os.getenv("SHEET_NAME", "Data Nota")
    WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Sheet1")
    GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

# Validasi API key
if not OPENAI_API_KEY:
    st.error("⚠️ OPENAI_API_KEY belum diset! Silakan set di file .env atau Streamlit Secrets.")
    st.stop()

# Inisialisasi OpenAI client
try:
    client = OpenAI(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL
    )
except Exception as e:
    st.error(f"Gagal inisialisasi OpenAI client: {e}")
    client = None

# ==========================================
# 2. FUNGSI HELPER (BACKEND LOGIC)
# ==========================================

def connect_to_gsheet():
    """Mengoneksikan Python ke Google Sheets"""
    try:
        if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
            st.error(f"File {GOOGLE_CREDENTIALS_FILE} tidak ditemukan. Silakan upload credentials Google Service Account.")
            return None
            
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client_gs = gspread.authorize(creds)
        
        sheet = client_gs.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
        return sheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Google Sheet '{SHEET_NAME}' tidak ditemukan. Pastikan sheet sudah dibuat dan service account sudah di-invite sebagai editor.")
        return None
    except Exception as e:
        st.error(f"Gagal konek ke Google Sheet: {e}")
        return None

def process_image_with_gpt4o(image_bytes, mime_type, model="gpt-4o"):
    """Mengirim gambar ke OpenAI GPT-4o/mini untuk diekstrak datanya"""
    
    if not client:
        st.error("OpenAI client belum diinisialisasi. Periksa API key Anda.")
        return None
    
    # Encode gambar ke base64
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    
    prompt_text = """
    Analisa gambar nota/invoice ini dengan SANGAT TELITI. Ekstrak SEMUA informasi yang ada.
    
    ⚠️ PERHATIAN KHUSUS UNTUK TULISAN TANGAN:
    - Nota ini kemungkinan TULISAN TANGAN yang sulit dibaca
    - Baca SETIAP karakter dengan EKSTRA HATI-HATI
    - Perhatikan konteks untuk memvalidasi pembacaan
    - Jika ada coretan atau angka yang ambigu, lihat pola keseluruhan
    - JANGAN tebak - jika tidak yakin, beri confidence rendah (<70)
    
    Output WAJIB format JSON Object dengan struktur berikut:
    
    {
      "metadata": {
        "tanggal": "YYYY-MM-DD atau DD/MM/YYYY (tanggal transaksi di nota)",
        "nama_toko": "Nama toko/merchant",
        "nomor_rekening": "Nomor rekening toko (jika ada)",
        "nama_bank": "Nama bank (jika ada, misal: BCA, Mandiri, BRI)",
        "pemilik_rekening": "Nama pemilik rekening (jika ada)",
        "jenis_pembayaran": "Cash atau Transfer",
        "confidence": {
          "tanggal": 0-100,
          "nama_toko": 0-100,
          "nomor_rekening": 0-100,
          "nama_bank": 0-100,
          "pemilik_rekening": 0-100,
          "jenis_pembayaran": 0-100
        }
      },
      "items": [
        {
          "nama_barang": "Nama produk/item",
          "qty": 1.0,
          "unit": "kg/pcs/liter/dll",
          "harga_satuan": 10000,
          "total_harga": 10000,
          "kategori_transaksi": "Bama atau Non Bama",
          "confidence": {
            "nama_barang": 0-100,
            "qty": 0-100,
            "unit": 0-100,
            "harga_satuan": 0-100,
            "total_harga": 0-100,
            "kategori_transaksi": 0-100
          }
        }
      ]
    }
    
    INSTRUKSI DETAIL:
    
    A. METADATA (Informasi Nota):
    1. 'tanggal': Tanggal transaksi di nota (format: YYYY-MM-DD atau DD/MM/YYYY)
       - PENTING: Cari di POJOK KIRI ATAS atau header nota
       - Format bisa: DD-MM-YYYY, DD/MM/YYYY, YYYY-MM-DD
       - Contoh: "09-11-2025" atau "09/11/2025" → "2025-11-09"
       - JANGAN buat tanggal sendiri - HARUS dari nota
       - Jika tidak ada, isi dengan null
    
    2. 'nama_toko': Nama toko/merchant
       - Biasanya di header paling atas
       - Jika tidak ada, isi dengan "Unknown"
    
    3. 'nomor_rekening': Nomor rekening toko (jika ada)
       - Cari di footer atau header
       - Jika tidak ada, isi dengan null
    
    4. 'nama_bank': Nama bank (BCA, Mandiri, BRI, BNI, dll)
       - Jika tidak ada, isi dengan null
    
    5. 'pemilik_rekening': Nama pemilik rekening
       - Jika tidak ada, isi dengan null
    
    6. 'jenis_pembayaran': "Cash" atau "Transfer"
       - Jika ada tulisan "Transfer", "QRIS", "Debit", "Credit", "Bank" = "Transfer"
       - Jika ada tulisan "Cash", "Tunai" = "Cash"
       - Jika tidak jelas, coba tebak dari konteks (ada nomor rekening = Transfer)
       - Default: "Cash"
    
    B. ITEMS (Daftar Barang):
    Untuk setiap item barang:
    
    1. 'nama_barang': Nama produk/item (string)
       - Baca SETIAP huruf dengan teliti
       - Perhatikan spasi dan kapitalisasi
       - Jangan singkat atau ubah nama
    
    2. 'qty': Jumlah/kuantitas barang (float)
       - Integer (1, 2, 3, dst) atau desimal (0.5, 1.5, dst)
       - Jika tertulis "1/2" = 0.5, "1/4" = 0.25
       - Default: 1
    
    3. 'unit': Satuan barang (string)
       - Contoh: "kg", "pcs", "liter", "gram", "box", "pack", "meter", dll
       - Jika qty dalam bentuk pecahan (0.5), kemungkinan unit adalah "kg" atau "liter"
       - Jika tidak ada, coba tebak dari nama barang atau isi "pcs"
    
    4. 'harga_satuan': Harga per unit (integer)
       - PERHATIAN: "20" atau "20k" kemungkinan = 20.000
       - Gunakan konteks total_harga untuk validasi
    
    5. 'total_harga': Total harga (qty × harga_satuan) (integer)
       - PERHATIAN: "20" atau "20k" kemungkinan = 20.000
    
    6. 'kategori_transaksi': "Bama" atau "Non Bama"
       - "Bama" = Bahan Makanan (beras, minyak, gula, sayur, buah, daging, ikan, telur, susu, dll)
       - "Non Bama" = Bukan Bahan Makanan (sabun, shampo, tissue, alat tulis, elektronik, dll)
       - Kategorikan berdasarkan nama barang
    
    7. 'confidence': Tingkat kepercayaan untuk setiap field (0-100)
       - Berikan confidence rendah (<70) jika:
         * Teks blur atau tidak jelas
         * Tulisan tangan yang sulit dibaca
         * Angka yang ambigu atau terpotong
         * Harus melakukan asumsi/tebakan
         * Format tidak standar
    
    TIPS OCR - PENTING UNTUK AKURASI:
    
    1. ANGKA yang sering tertukar:
       - "0" (nol) vs "O" (huruf O) → Lihat konteks (di angka = 0, di kata = O)
       - "1" (satu) vs "l" (huruf L kecil) vs "I" (huruf i besar) → Lihat konteks
       - "5" (lima) vs "S" (huruf S) → Di angka = 5, di kata = S
       - "8" (delapan) vs "B" (huruf B) → Di angka = 8, di kata = B
       - "6" (enam) vs "G" (huruf G) → Di angka = 6, di kata = G
    
    2. NAMA BARANG - Baca dengan teliti:
       - "Beras Premium" BUKAN "Beras Premum" atau "Beras Premlum"
       - "Minyak Goreng" BUKAN "Mlnyak Goreng" atau "Minyak Goreng"
       - Perhatikan ejaan yang benar
    
    3. QUANTITY - Validasi dengan total:
       - Jika qty=5, harga_satuan=10000, maka total_harga HARUS 50000
       - Jika tidak match, kemungkinan qty atau harga salah baca
    
    4. HARGA - Perhatikan pemisah ribuan:
       - "15.000" atau "15,000" atau "15000" = 15000
       - "20k" atau "20rb" = 20000
       - Jangan lupa hapus pemisah ribuan
    
    ATURAN KHUSUS HARGA:
    - Jika harga tertulis "20", "25", "30" dll (angka kecil), cek apakah masuk akal
    - Jika total_harga jauh lebih besar, kemungkinan harga dalam ribuan (20 = 20.000)
    - Jika ada notasi "k" atau "rb", kalikan dengan 1000 (20k = 20000)
    - Pastikan qty × harga_satuan = total_harga
    - Format dengan titik/koma (15.000 atau 15,000) → 15000
    
    YANG DIABAIKAN:
    - Subtotal, pajak (tax/PPN), diskon, total pembayaran akhir
    - Informasi kasir, tanda tangan
    
    Contoh output:
    {
      "metadata": {
        "tanggal": "2024-01-15",
        "nama_toko": "Toko Sumber Rezeki",
        "nomor_rekening": "1234567890",
        "nama_bank": "BCA",
        "pemilik_rekening": "Budi Santoso",
        "jenis_pembayaran": "Transfer",
        "confidence": {
          "tanggal": 95,
          "nama_toko": 100,
          "nomor_rekening": 90,
          "nama_bank": 95,
          "pemilik_rekening": 85,
          "jenis_pembayaran": 80
        }
      },
      "items": [
        {
          "nama_barang": "Beras Premium",
          "qty": 5,
          "unit": "kg",
          "harga_satuan": 15000,
          "total_harga": 75000,
          "kategori_transaksi": "Bama",
          "confidence": {
            "nama_barang": 95,
            "qty": 100,
            "unit": 90,
            "harga_satuan": 90,
            "total_harga": 90,
            "kategori_transaksi": 100
          }
        },
        {
          "nama_barang": "Minyak Goreng",
          "qty": 2,
          "unit": "liter",
          "harga_satuan": 25000,
          "total_harga": 50000,
          "kategori_transaksi": "Bama",
          "confidence": {
            "nama_barang": 100,
            "qty": 100,
            "unit": 95,
            "harga_satuan": 95,
            "total_harga": 95,
            "kategori_transaksi": 100
          }
        }
      ]
    }
    
    Jika tidak ada item: {"metadata": {...}, "items": []}
    """

    try:
        response = client.chat.completions.create(
            model=model,  # Gunakan model yang dipilih user
            messages=[
                {
                    "role": "system",
                    "content": """Anda adalah AI expert untuk OCR nota belanja Indonesia. 
                    Tugas Anda: Ekstrak data dengan SANGAT TELITI dan AKURAT.
                    
                    PENTING:
                    - Baca SETIAP karakter dengan hati-hati
                    - Jangan skip atau asumsikan data
                    - Jika ragu, beri confidence rendah
                    - Perhatikan konteks untuk validasi (misal: harga harus masuk akal)
                    """
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}",
                            "detail": "high"  # PENTING: Gunakan detail tinggi untuk akurasi maksimal
                        }}
                    ],
                }
            ],
            response_format={"type": "json_object"},
            temperature=0,  # 0 untuk konsistensi maksimal
            max_tokens=4096  # Cukup untuk nota panjang
        )
        
        result_content = response.choices[0].message.content
        parsed_result = json.loads(result_content)
        
        # Validasi struktur response
        if 'items' not in parsed_result:
            st.warning("Response dari AI tidak sesuai format. Mencoba ekstrak data...")
            return {"items": []}
            
        return parsed_result
        
    except json.JSONDecodeError as e:
        st.error(f"Error parsing JSON dari OpenAI: {e}")
        return None
    except Exception as e:
        st.error(f"Error saat memanggil OpenAI API: {e}")
        return None

def convert_pdf_to_image(pdf_bytes):
    """Mengubah halaman pertama PDF menjadi gambar (bytes)"""
    try:
        images = convert_from_bytes(pdf_bytes, dpi=300)  # DPI tinggi untuk kualitas OCR lebih baik
        if images:
            # Ambil halaman pertama saja
            first_page = images[0]
            img_byte_arr = BytesIO()
            first_page.save(img_byte_arr, format='JPEG', quality=95)
            return img_byte_arr.getvalue(), "image/jpeg"
        return None, None
    except Exception as e:
        st.error(f"Error konversi PDF: {e}")
        st.info("Pastikan Poppler sudah terinstall. Di macOS: brew install poppler")
        return None, None

def validate_and_correct_items(items):
    """
    Validasi dan koreksi otomatis data hasil ekstraksi AI.
    
    Menangani:
    1. Hyper-efficiency: Harga "20" yang sebenarnya "20.000" 
    2. Kuantitas abstrak: "1/2" atau "0.5" untuk setengah
    3. Balance check: qty × harga_satuan = total_harga
    4. Confidence score: Mempertahankan skor kepercayaan dari AI
    5. Field baru: unit, kategori_transaksi
    
    Returns:
        list: Items yang sudah dikoreksi
        list: Log koreksi yang dilakukan
    """
    corrected_items = []
    correction_logs = []
    
    for idx, item in enumerate(items):
        original_item = item.copy()
        
        # Pastikan semua field ada
        nama = item.get('nama_barang', f'Item {idx+1}')
        qty = item.get('qty', 1)
        unit = item.get('unit', 'pcs')
        harga_satuan = item.get('harga_satuan', 0)
        total_harga = item.get('total_harga', 0)
        kategori = item.get('kategori_transaksi', 'Non Bama')
        
        # Ambil confidence score jika ada, atau buat default
        confidence = item.get('confidence', {
            'nama_barang': 100,
            'qty': 100,
            'unit': 100,
            'harga_satuan': 100,
            'total_harga': 100,
            'kategori_transaksi': 100
        })
        
        # Pastikan confidence adalah dict
        if not isinstance(confidence, dict):
            confidence = {
                'nama_barang': 100,
                'qty': 100,
                'unit': 100,
                'harga_satuan': 100,
                'total_harga': 100,
                'kategori_transaksi': 100
            }
        
        # Convert ke numeric jika masih string
        try:
            qty = float(qty) if not isinstance(qty, (int, float)) else qty
            harga_satuan = int(harga_satuan) if not isinstance(harga_satuan, (int, float)) else harga_satuan
            total_harga = int(total_harga) if not isinstance(total_harga, (int, float)) else total_harga
        except:
            correction_logs.append(f"⚠️ Item '{nama}': Gagal convert ke numeric, skip")
            continue
        
        # KOREKSI 1: Deteksi hyper-efficiency pada harga_satuan
        # Jika harga_satuan < 1000 tapi total_harga > 10000, kemungkinan harga dalam ribuan
        if harga_satuan < 1000 and total_harga > 10000:
            # Cek apakah total_harga adalah kelipatan ribuan dari harga_satuan
            multiplier = total_harga / (harga_satuan * qty) if qty > 0 else 0
            
            # Jika multiplier mendekati 1000, berarti harga_satuan seharusnya dikali 1000
            if 900 <= multiplier <= 1100:
                old_harga = harga_satuan
                harga_satuan = harga_satuan * 1000
                correction_logs.append(
                    f"✅ '{nama}': Harga satuan dikoreksi {old_harga} → {harga_satuan:,} (hyper-efficiency)"
                )
                # Turunkan confidence karena ada koreksi
                confidence['harga_satuan'] = min(confidence.get('harga_satuan', 100), 80)
        
        # KOREKSI 2: Deteksi hyper-efficiency pada total_harga
        # Jika total_harga < 1000 tapi harga_satuan > 10000
        if total_harga < 1000 and harga_satuan > 10000:
            multiplier = (harga_satuan * qty) / total_harga if total_harga > 0 else 0
            
            if 900 <= multiplier <= 1100:
                old_total = total_harga
                total_harga = total_harga * 1000
                correction_logs.append(
                    f"✅ '{nama}': Total harga dikoreksi {old_total} → {total_harga:,} (hyper-efficiency)"
                )
                # Turunkan confidence karena ada koreksi
                confidence['total_harga'] = min(confidence.get('total_harga', 100), 80)
        
        # KOREKSI 3: Balance check - qty × harga_satuan = total_harga
        expected_total = qty * harga_satuan
        
        # Toleransi 5% untuk pembulatan
        tolerance = 0.05
        diff_ratio = abs(expected_total - total_harga) / expected_total if expected_total > 0 else 0
        
        if diff_ratio > tolerance:
            # Ada ketidaksesuaian, tentukan mana yang benar
            
            # Strategi: Percaya total_harga, koreksi harga_satuan
            # Karena biasanya total_harga lebih akurat di nota
            if total_harga > 0 and qty > 0:
                old_harga_satuan = harga_satuan
                harga_satuan = int(total_harga / qty)
                
                correction_logs.append(
                    f"⚖️ '{nama}': Balance dikoreksi - Harga satuan {old_harga_satuan:,} → {harga_satuan:,} "
                    f"(qty={qty}, total={total_harga:,})"
                )
                # Turunkan confidence karena ada koreksi
                confidence['harga_satuan'] = min(confidence.get('harga_satuan', 100), 70)
            # Jika total_harga = 0, hitung dari qty × harga_satuan
            elif total_harga == 0 and harga_satuan > 0:
                total_harga = int(qty * harga_satuan)
                correction_logs.append(
                    f"⚖️ '{nama}': Total harga dihitung = {total_harga:,} (dari qty × harga_satuan)"
                )
                # Turunkan confidence karena ada koreksi
                confidence['total_harga'] = min(confidence.get('total_harga', 100), 70)
        
        # Simpan item yang sudah dikoreksi dengan confidence score
        corrected_items.append({
            'nama_barang': nama,
            'qty': qty,
            'unit': unit,
            'harga_satuan': int(harga_satuan),
            'total_harga': int(total_harga),
            'kategori_transaksi': kategori,
            'confidence': confidence
        })
    
    return corrected_items, correction_logs

def prepare_dataframe_with_confidence(items, metadata=None):
    """
    Menyiapkan DataFrame dengan kolom confidence indicator dan metadata.
    
    Menambahkan emoji/simbol untuk menandai field dengan confidence rendah:
    - 🟢 (>= 80): Confidence tinggi
    - 🟡 (70-79): Confidence sedang
    - 🔴 (< 70): Confidence rendah - perlu review
    
    Args:
        items: List of dict dengan confidence score
        metadata: Dict dengan informasi nota (tanggal, nama_toko, dll)
        
    Returns:
        DataFrame dengan kolom lengkap sesuai urutan yang dibutuhkan
    """
    df_data = []
    
    # Default metadata jika tidak ada
    if metadata is None:
        metadata = {
            'tanggal': None,
            'nama_toko': 'Unknown',
            'nomor_rekening': None,
            'nama_bank': None,
            'pemilik_rekening': None,
            'jenis_pembayaran': 'Cash'
        }
    
    for item in items:
        confidence = item.get('confidence', {})
        
        # Buat visual indicator untuk setiap field
        nama_conf = confidence.get('nama_barang', 100)
        qty_conf = confidence.get('qty', 100)
        unit_conf = confidence.get('unit', 100)
        harga_conf = confidence.get('harga_satuan', 100)
        total_conf = confidence.get('total_harga', 100)
        kategori_conf = confidence.get('kategori_transaksi', 100)
        
        # Fungsi untuk mendapatkan emoji berdasarkan confidence
        def get_indicator(conf_score):
            if conf_score >= 80:
                return ""  # Tidak perlu indicator jika confidence tinggi
            elif conf_score >= 70:
                return "⚠️"  # Warning untuk confidence sedang
            else:
                return "❗"  # Alert untuk confidence rendah
        
        # Tambahkan indicator ke field yang perlu
        nama_display = item.get('nama_barang', '')
        indicator = get_indicator(nama_conf)
        if indicator:
            nama_display = f"{indicator} {nama_display}"
        
        unit_display = item.get('unit', 'pcs')
        unit_indicator = get_indicator(unit_conf)
        if unit_indicator:
            unit_display = f"{unit_indicator} {unit_display}"
        
        kategori_display = item.get('kategori_transaksi', 'Non Bama')
        kategori_indicator = get_indicator(kategori_conf)
        if kategori_indicator:
            kategori_display = f"{kategori_indicator} {kategori_display}"
        
        # Urutan kolom sesuai kebutuhan:
        # Tanggal, Nama Toko, Nomor Rekening, Nama Bank, Pemilik Rekening, 
        # Jenis Pembayaran, Kategori Transaksi, Quantity, Unit, Nama Barang, 
        # Harga Satuan, Harga Total
        row = {
            'tanggal': metadata.get('tanggal'),
            'nama_toko': metadata.get('nama_toko', 'Unknown'),
            'nomor_rekening': metadata.get('nomor_rekening'),
            'nama_bank': metadata.get('nama_bank'),
            'pemilik_rekening': metadata.get('pemilik_rekening'),
            'jenis_pembayaran': metadata.get('jenis_pembayaran', 'Cash'),
            'kategori_transaksi': kategori_display,
            'qty': item.get('qty', 1),
            'unit': unit_display,
            'nama_barang': nama_display,
            'harga_satuan': item.get('harga_satuan', 0),
            'total_harga': item.get('total_harga', 0),
            # Simpan confidence untuk referensi (hidden)
            '_conf_nama': nama_conf,
            '_conf_qty': qty_conf,
            '_conf_unit': unit_conf,
            '_conf_harga': harga_conf,
            '_conf_total': total_conf,
            '_conf_kategori': kategori_conf,
            # Simpan nilai asli tanpa indicator
            '_nama_asli': item.get('nama_barang', ''),
            '_unit_asli': item.get('unit', 'pcs'),
            '_kategori_asli': item.get('kategori_transaksi', 'Non Bama')
        }
        
        # Tambahkan source_file jika ada (untuk batch mode)
        if 'source_file' in item:
            row['source_file'] = item['source_file']
        
        df_data.append(row)
    
    return pd.DataFrame(df_data)

def validate_dataframe(df):
    """Validasi data hasil ekstraksi"""
    if df is None or df.empty:
        return False, "Tidak ada data yang diekstrak"
    
    required_columns = ['nama_barang', 'qty', 'harga_satuan', 'total_harga']
    missing_cols = [col for col in required_columns if col not in df.columns]
    
    if missing_cols:
        return False, f"Kolom yang hilang: {', '.join(missing_cols)}"
    
    return True, "Valid"

# ==========================================
# 3. USER INTERFACE (STREAMLIT)
# ==========================================

st.set_page_config(
    page_title="AI Nota Scanner", 
    layout="wide",
    page_icon="🧾",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

# Force light theme
st.markdown("""
    <script>
        var elements = window.parent.document.querySelectorAll('.stApp');
        elements[0].classList.remove('dark-theme');
    </script>
""", unsafe_allow_html=True)

# Custom CSS - Clean & Professional Purple Theme
st.markdown("""
    <style>
    /* Import Google Fonts - Poppins untuk modern & clean look */
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');
    
    /* Global */
    * {
        font-family: 'Poppins', sans-serif;
    }
    
    /* Background */
    .stApp {
        background: #f8f9fc;
    }
    
    /* Main Container */
    .main .block-container {
        max-width: 1200px;
        padding: 2rem;
        background: white;
        margin: 1rem auto;
    }
    
    /* Title */
    h1 {
        color: #6b46c1;
        font-weight: 700;
        font-size: 2.5rem !important;
        margin-bottom: 0.5rem;
    }
    
    /* Subtitle */
    .subtitle {
        color: #64748b;
        font-size: 1rem;
        margin-bottom: 2rem;
        font-weight: 400;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #6b46c1;
    }
    
    [data-testid="stSidebar"] .block-container {
        padding: 1.5rem 1rem;
    }
    
    [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] h3 {
        color: white !important;
        font-weight: 600;
    }
    
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stMarkdown {
        color: rgba(255, 255, 255, 0.95) !important;
    }
    
    /* Buttons */
    .stButton > button {
        background: #6b46c1;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.6rem 1.5rem;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    
    .stButton > button:hover {
        background: #553c9a;
        box-shadow: 0 4px 12px rgba(107, 70, 193, 0.3);
    }
    
    /* Primary Button */
    .stButton > button[kind="primary"] {
        background: #7c3aed;
    }
    
    .stButton > button[kind="primary"]:hover {
        background: #6d28d9;
    }
    
    /* Headers */
    h2, h3 {
        color: #6b46c1;
        font-weight: 600;
    }
    
    /* Metrics */
    [data-testid="stMetric"] {
        background: #f3f4f6;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #6b46c1;
    }
    
    [data-testid="stMetricLabel"] {
        color: #64748b;
        font-weight: 500;
    }
    
    [data-testid="stMetricValue"] {
        color: #6b46c1;
        font-weight: 700;
    }
    
    /* Data Editor */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #e5e7eb;
    }
    
    /* File Uploader */
    [data-testid="stFileUploader"] {
        background: #1f2937;
        border: 2px dashed #6b46c1;
        border-radius: 8px;
        padding: 1.5rem;
    }
    
    [data-testid="stFileUploader"] label {
        color: white !important;
        font-weight: 600;
    }
    
    [data-testid="stFileUploader"] small {
        color: white !important;
        font-weight: 500;
    }
    
    [data-testid="stFileUploader"] button {
        background: #6b46c1 !important;
        color: white !important;
        border: none !important;
        font-weight: 600;
    }
    
    [data-testid="stFileUploader"] section {
        color: white !important;
        background: #1f2937 !important;
    }
    
    [data-testid="stFileUploader"] span {
        color: white !important;
    }
    
    [data-testid="stFileUploader"] p {
        color: white !important;
    }
    
    [data-testid="stFileUploader"] div {
        color: white !important;
        background: #1f2937 !important;
    }
    
    [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
        background: #1f2937 !important;
        border: 2px dashed rgba(107, 70, 193, 0.5) !important;
    }
    
    [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzoneInstructions"] {
        color: white !important;
    }
    
    /* Progress Bar */
    .stProgress > div > div {
        background: #6b46c1;
    }
    
    /* Info Alert */
    .stAlert[data-baseweb="notification"] {
        background: #faf5ff;
        border-left: 4px solid #6b46c1;
        color: #1f2937;
    }
    
    /* Success Alert */
    [data-testid="stAlert"][kind="success"] {
        background: #f0fdf4;
        border-left: 4px solid #10b981;
        color: #1f2937;
    }
    
    /* Error Alert */
    [data-testid="stAlert"][kind="error"] {
        background: #fef2f2;
        border-left: 4px solid #ef4444;
        color: #1f2937;
    }
    
    /* Warning Alert */
    [data-testid="stAlert"][kind="warning"] {
        background: #fffbeb;
        border-left: 4px solid #f59e0b;
        color: #1f2937;
    }
    
    /* Divider */
    hr {
        border-color: #e5e7eb;
        margin: 1.5rem 0;
    }
    
    /* Expander */
    .streamlit-expanderHeader {
        background: #f9fafb;
        border-radius: 8px;
        color: #6b46c1;
        font-weight: 600;
        border: 1px solid #e5e7eb;
    }
    
    /* Image */
    [data-testid="stImage"] {
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* Caption text */
    small, .caption {
        color: #64748b;
    }
    
    /* Force light mode - prevent theme switching */
    @media (prefers-color-scheme: dark) {
        .stApp {
            background: #f8f9fc !important;
        }
        
        .main .block-container {
            background: white !important;
            color: #1f2937 !important;
        }
        
        h1, h2, h3, h4, h5, h6 {
            color: #6b46c1 !important;
        }
        
        p, span, div, label {
            color: #1f2937 !important;
        }
        
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] div,
        [data-testid="stSidebar"] label {
            color: white !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

# Header
st.markdown("<h1>📄 Nota Scanner</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>Konversi nota menjadi data digital secara otomatis</p>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

# --- SIDEBAR: UPLOAD & INFO ---
with st.sidebar:
    st.header("📤 Upload File Nota")
    uploaded_files = st.file_uploader(
        "Pilih file Nota/Invoice", 
        type=["jpg", "png", "jpeg", "pdf"],
        accept_multiple_files=True,
        help="Format yang didukung: JPG, PNG, PDF. Bisa upload beberapa file sekaligus!"
    )
    
    st.markdown("---")
    st.markdown("### 🤖 Pilih Model AI")
    
    model_choice = st.selectbox(
        "Model OCR",
        options=["GPT-4o-mini (Hemat Biaya)", "GPT-4o (Recommended)"],
        index=0,
        help="Pilih model AI untuk ekstraksi data"
    )
    
    # Info model - hanya biaya
    if "GPT-4o" in model_choice and "mini" not in model_choice:
        st.caption("💰 Biaya: ~$0.01-0.02 per nota")
        selected_model = "gpt-4o"
    else:
        st.caption("� Biaya: ~$0.001-0.002 per nota")
        selected_model = "gpt-4o-mini"
    
    # Status
    st.markdown("---")
    st.markdown("### 🔌 Status")
    
    if OPENAI_API_KEY and OPENAI_API_KEY != "sk-...":
        st.success("✓ API Terhubung")
    else:
        st.error("✗ API Belum Diset")
    
    if os.path.exists(GOOGLE_CREDENTIALS_FILE):
        st.success("✓ Google Sheet Ready")
    else:
        st.warning("! Credentials Belum Ada")

# --- MAIN AREA ---

# Inisialisasi Session State
if 'ocr_result_df' not in st.session_state:
    st.session_state.ocr_result_df = None
if 'scan_timestamp' not in st.session_state:
    st.session_state.scan_timestamp = None
if 'all_results' not in st.session_state:
    st.session_state.all_results = []

if uploaded_files:
    # Info jumlah file
    st.info(f"📁 {len(uploaded_files)} file ter-upload. Klik 'Scan Semua' untuk memproses.")
    
    # Tab untuk setiap file
    if len(uploaded_files) == 1:
        # Single file mode (tampilan seperti sebelumnya)
        uploaded_file = uploaded_files[0]
        
        # 1. Preview File
        col1, col2 = st.columns([1, 2])
        
        image_bytes = None
        mime_type = None

        with col1:
            st.subheader("📷 Preview File")
            
            if uploaded_file.type == "application/pdf":
                # Konversi PDF ke gambar
                pdf_bytes = uploaded_file.getvalue()
                image_bytes, mime_type = convert_pdf_to_image(pdf_bytes)
                if image_bytes:
                    st.image(image_bytes, caption="Halaman 1 dari PDF", use_container_width=True)
                else:
                    st.error("Gagal mengkonversi PDF ke gambar")
            else:
                # Langsung tampilkan gambar
                image_bytes = uploaded_file.getvalue()
                mime_type = uploaded_file.type
                st.image(uploaded_file, caption="Uploaded Image", use_container_width=True)
            
            # Info file
            file_size = len(uploaded_file.getvalue()) / 1024  # KB
            st.caption(f"📄 {uploaded_file.name} ({file_size:.1f} KB)")

        # 2. Tombol Scan & Hasil
        with col2:
            st.subheader("🤖 Ekstraksi Data dengan AI")
            
            # Tombol Scan
            scan_button = st.button(
                "🔍 Scan Nota dengan AI", 
                type="primary",
                use_container_width=True,
                disabled=(image_bytes is None)
            )
            
            if scan_button and image_bytes:
                with st.spinner("🔄 Sedang menganalisa nota dengan AI... Mohon tunggu..."):
                    json_data = process_image_with_gpt4o(image_bytes, mime_type, selected_model)
                    
                    if json_data and 'items' in json_data:
                        items = json_data['items']
                        metadata = json_data.get('metadata', {})
                        
                        if len(items) == 0:
                            st.warning("⚠️ Tidak ada item yang berhasil diekstrak. Coba foto/PDF yang lebih jelas.")
                        else:
                            # Validasi dan koreksi otomatis
                            corrected_items, correction_logs = validate_and_correct_items(items)
                            
                            # Convert ke Pandas DataFrame dengan confidence indicator dan metadata
                            df = prepare_dataframe_with_confidence(corrected_items, metadata)
                            
                            # Validasi
                            is_valid, msg = validate_dataframe(df)
                            if is_valid:
                                st.session_state.ocr_result_df = df
                                st.session_state.scan_timestamp = datetime.now()
                                st.success(f"✅ Berhasil! Ditemukan {len(df)} item.")
                                
                                # Tampilkan info metadata
                                if metadata:
                                    with st.expander("📋 Informasi Nota", expanded=False):
                                        col_meta1, col_meta2 = st.columns(2)
                                        with col_meta1:
                                            st.write(f"**Tanggal:** {metadata.get('tanggal', '-')}")
                                            st.write(f"**Nama Toko:** {metadata.get('nama_toko', '-')}")
                                            st.write(f"**Jenis Pembayaran:** {metadata.get('jenis_pembayaran', '-')}")
                                        with col_meta2:
                                            st.write(f"**Nomor Rekening:** {metadata.get('nomor_rekening', '-')}")
                                            st.write(f"**Nama Bank:** {metadata.get('nama_bank', '-')}")
                                            st.write(f"**Pemilik Rekening:** {metadata.get('pemilik_rekening', '-')}")
                                
                                # Hitung berapa field yang perlu review (confidence < 80)
                                low_conf_count = 0
                                for item in corrected_items:
                                    conf = item.get('confidence', {})
                                    for field, score in conf.items():
                                        if score < 80:
                                            low_conf_count += 1
                                
                                # Tambahkan confidence dari metadata
                                if metadata and 'confidence' in metadata:
                                    for field, score in metadata['confidence'].items():
                                        if score < 80:
                                            low_conf_count += 1
                                
                                if low_conf_count > 0:
                                    st.warning(f"⚠️ {low_conf_count} field memiliki confidence rendah. Ditandai dengan ⚠️ atau ❗. Silakan review!")
                                
                                # Tampilkan log koreksi jika ada
                                if correction_logs:
                                    with st.expander(f"🔧 Koreksi Otomatis ({len(correction_logs)} perubahan)", expanded=True):
                                        for log in correction_logs:
                                            st.write(log)
                            else:
                                st.error(f"❌ Validasi gagal: {msg}")
                    else:
                        st.error("❌ Gagal mendapatkan data dari AI. Coba lagi.")

            
            # Info hasil scan terakhir
            if st.session_state.scan_timestamp:
                st.info(f"📅 Scan terakhir: {st.session_state.scan_timestamp.strftime('%H:%M:%S')}")
    
    else:
        # BATCH MODE - Multiple files
        st.markdown("---")
        st.subheader(f"📦 Batch Processing Mode - {len(uploaded_files)} Files")
        
        # Preview thumbnails
        cols = st.columns(min(len(uploaded_files), 5))
        for idx, file in enumerate(uploaded_files[:5]):
            with cols[idx]:
                try:
                    if file.type == "application/pdf":
                        st.caption(f"📄 {file.name[:15]}...")
                    else:
                        st.image(file, caption=file.name[:15]+"...", use_container_width=True)
                except:
                    st.caption(f"📄 {file.name[:15]}...")
        
        if len(uploaded_files) > 5:
            st.caption(f"... dan {len(uploaded_files) - 5} file lainnya")
        
        # Batch scan button
        st.markdown("---")
        col_batch1, col_batch2 = st.columns([3, 1])
        
        with col_batch1:
            st.write("**Scan semua nota sekaligus dengan AI**")
            st.caption(f"Total: {len(uploaded_files)} file akan diproses")
        
        with col_batch2:
            batch_scan_button = st.button(
                "🚀 Scan Semua",
                type="primary",
                use_container_width=True
            )
        
        if batch_scan_button:
            all_items = []
            all_correction_logs = []
            all_metadata_list = []  # Simpan metadata per file
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for idx, file in enumerate(uploaded_files):
                status_text.text(f"⏳ Memproses {idx + 1}/{len(uploaded_files)}: {file.name}")
                
                # Get image bytes
                try:
                    if file.type == "application/pdf":
                        pdf_bytes = file.getvalue()
                        img_bytes, img_mime = convert_pdf_to_image(pdf_bytes)
                    else:
                        img_bytes = file.getvalue()
                        img_mime = file.type
                    
                    if img_bytes:
                        # Process with AI
                        json_data = process_image_with_gpt4o(img_bytes, img_mime, selected_model)
                        
                        if json_data and 'items' in json_data:
                            items = json_data['items']
                            metadata = json_data.get('metadata', {})
                            
                            # Validasi dan koreksi otomatis
                            corrected_items, correction_logs = validate_and_correct_items(items)
                            
                            # Tambahkan metadata dan source file ke setiap item
                            for item in corrected_items:
                                item['source_file'] = file.name
                                # Simpan metadata dalam item untuk batch mode
                                item['_metadata'] = metadata
                            
                            all_items.extend(corrected_items)
                            
                            # Simpan log koreksi dengan info file
                            for log in correction_logs:
                                all_correction_logs.append(f"[{file.name}] {log}")
                    
                except Exception as e:
                    st.warning(f"⚠️ Error pada {file.name}: {e}")
                
                progress_bar.progress((idx + 1) / len(uploaded_files))
            
            # Combine results
            if all_items:
                # Untuk batch mode, kita perlu handle metadata per-item
                # Karena setiap file bisa punya metadata berbeda
                df_rows = []
                for item in all_items:
                    item_metadata = item.pop('_metadata', {})
                    # Prepare single item dengan metadata-nya
                    df_single = prepare_dataframe_with_confidence([item], item_metadata)
                    df_rows.append(df_single)
                
                # Gabungkan semua dataframe
                df_combined = pd.concat(df_rows, ignore_index=True)
                
                st.session_state.ocr_result_df = df_combined
                st.session_state.scan_timestamp = datetime.now()
                
                status_text.empty()
                progress_bar.empty()
                st.success(f"✅ Berhasil! Total {len(df_combined)} item dari {len(uploaded_files)} file.")
                
                # Hitung berapa field yang perlu review (confidence < 80)
                low_conf_count = 0
                for item in all_items:
                    conf = item.get('confidence', {})
                    for field, score in conf.items():
                        if score < 80:
                            low_conf_count += 1
                
                if low_conf_count > 0:
                    st.warning(f"⚠️ {low_conf_count} field memiliki confidence rendah. Ditandai dengan ⚠️ atau ❗. Silakan review!")
                
                # Tampilkan log koreksi jika ada
                if all_correction_logs:
                    with st.expander(f"🔧 Koreksi Otomatis ({len(all_correction_logs)} perubahan)", expanded=False):
                        for log in all_correction_logs:
                            st.write(log)
                
                st.balloons()
            else:
                status_text.empty()
                progress_bar.empty()
                st.error("❌ Tidak ada item yang berhasil diekstrak dari semua file.")



    # 3. Data Editor (Editable Table)
    if st.session_state.ocr_result_df is not None:
        st.markdown("---")
        st.subheader("📊 Hasil Ekstraksi Data")
        
        # Legend untuk confidence indicator
        col_legend1, col_legend2 = st.columns([3, 1])
        with col_legend1:
            st.info("💡 **Tips:** Klik cell untuk mengedit. Tekan Enter untuk konfirmasi. Klik '+' untuk tambah baris.")
        with col_legend2:
            st.markdown("""
            **Legend:**  
            ❗ = Perlu Review  
            ⚠️ = Cek Ulang
            """)
        
        # Prepare dataframe untuk display (tanpa kolom internal)
        display_df = st.session_state.ocr_result_df.copy()
        
        # Hapus kolom internal yang dimulai dengan underscore
        cols_to_hide = [col for col in display_df.columns if col.startswith('_')]
        display_df = display_df.drop(columns=cols_to_hide, errors='ignore')
        
        # Widget Data Editor - Urutan kolom sesuai kebutuhan
        column_config = {
            "tanggal": st.column_config.TextColumn("Tanggal", width="medium", help="Format: YYYY-MM-DD atau DD/MM/YYYY"),
            "nama_toko": st.column_config.TextColumn("Nama Toko", width="medium", required=True),
            "nomor_rekening": st.column_config.TextColumn("Nomor Rekening", width="medium"),
            "nama_bank": st.column_config.TextColumn("Nama Bank", width="small"),
            "pemilik_rekening": st.column_config.TextColumn("Pemilik Rekening", width="medium"),
            "jenis_pembayaran": st.column_config.SelectboxColumn(
                "Jenis Pembayaran", 
                width="small",
                options=["Cash", "Transfer"],
                required=True
            ),
            "kategori_transaksi": st.column_config.SelectboxColumn(
                "Kategori", 
                width="small",
                options=["Bama", "Non Bama"],
                required=True
            ),
            "qty": st.column_config.NumberColumn("Qty", width="small", min_value=0.01, required=True),
            "unit": st.column_config.TextColumn("Unit", width="small", required=True),
            "nama_barang": st.column_config.TextColumn("Nama Barang", width="large", required=True),
            "harga_satuan": st.column_config.NumberColumn("Harga Satuan (Rp)", width="medium", format="%d", required=True),
            "total_harga": st.column_config.NumberColumn("Total Harga (Rp)", width="medium", format="%d", required=True),
        }
        
        # Tambahkan kolom source_file jika ada (untuk batch mode)
        if 'source_file' in display_df.columns:
            column_config["source_file"] = st.column_config.TextColumn("File Asal", width="medium")
        
        edited_df = st.data_editor(
            display_df,
            num_rows="dynamic",  # User bisa tambah/hapus baris
            use_container_width=True,
            column_config=column_config,
            hide_index=False,
        )
        
        # Auto-recalculate total_harga berdasarkan qty × harga_satuan
        if 'qty' in edited_df.columns and 'harga_satuan' in edited_df.columns and 'total_harga' in edited_df.columns:
            # Recalculate total_harga
            edited_df['total_harga'] = (edited_df['qty'] * edited_df['harga_satuan']).astype(int)
            st.info("💡 Total harga otomatis dihitung ulang: Qty × Harga Satuan")
        
        # Summary
        col_sum1, col_sum2, col_sum3 = st.columns(3)
        with col_sum1:
            st.metric("Total Items", len(edited_df))
        with col_sum2:
            total_qty = edited_df['qty'].sum() if 'qty' in edited_df.columns else 0
            st.metric("Total Quantity", int(total_qty))
        with col_sum3:
            grand_total = edited_df['total_harga'].sum() if 'total_harga' in edited_df.columns else 0
            st.metric("Grand Total", f"Rp {grand_total:,.0f}")

        # 4. Save to Google Sheet
        st.markdown("---")
        col_save1, col_save2 = st.columns([3, 1])
        
        with col_save1:
            st.write("**Simpan data ke Google Sheets**")
            st.caption("Data akan ditambahkan ke sheet sebagai baris baru (append mode)")
        
        with col_save2:
            save_button = st.button("💾 Simpan ke Google Sheet", type="primary", use_container_width=True)
        
        if save_button:
            if edited_df.empty:
                st.error("❌ Tidak ada data untuk disimpan")
            else:
                sheet = connect_to_gsheet()
                if sheet:
                    try:
                        # Bersihkan emoji indicator dari field yang mungkin punya emoji
                        save_df = edited_df.copy()
                        
                        # Hapus emoji ⚠️ dan ❗ dari semua field text
                        text_columns = ['nama_barang', 'unit', 'kategori_transaksi']
                        for col in text_columns:
                            if col in save_df.columns:
                                save_df[col] = save_df[col].astype(str).str.replace('⚠️ ', '', regex=False)
                                save_df[col] = save_df[col].astype(str).str.replace('❗ ', '', regex=False)
                        
                        # Append ke sheet (tanpa timestamp karena sudah ada kolom tanggal)
                        rows_to_append = save_df.values.tolist()
                        sheet.append_rows(rows_to_append)
                        
                        st.balloons()
                        st.success(f"✅ Berhasil menyimpan {len(edited_df)} item ke Google Sheet: **{SHEET_NAME}**")
                        
                        # Opsional: Reset setelah save
                        if st.checkbox("Reset data setelah save?"):
                            st.session_state.ocr_result_df = None
                            st.session_state.scan_timestamp = None
                            st.rerun()
                            
                    except Exception as e:
                        st.error(f"❌ Gagal menyimpan data: {e}")

else:
    # Welcome screen
    st.info("👈 Silakan upload file nota di sidebar untuk memulai")
    
    st.markdown("### 💼 Fitur Utama")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div style='background: #faf5ff; padding: 1.5rem; border-radius: 8px; text-align: center; border: 1px solid #e9d5ff;'>
            <div style='font-size: 2.5rem; margin-bottom: 0.5rem;'>📸</div>
            <h4 style='color: #6b46c1; margin-bottom: 0.5rem; font-size: 1rem;'>Upload</h4>
            <p style='color: #64748b; font-size: 0.85rem; margin: 0;'>Foto atau PDF nota</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style='background: #faf5ff; padding: 1.5rem; border-radius: 8px; text-align: center; border: 1px solid #e9d5ff;'>
            <div style='font-size: 2.5rem; margin-bottom: 0.5rem;'>⚡</div>
            <h4 style='color: #6b46c1; margin-bottom: 0.5rem; font-size: 1rem;'>Ekstrak</h4>
            <p style='color: #64748b; font-size: 0.85rem; margin: 0;'>Data otomatis dengan AI</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div style='background: #faf5ff; padding: 1.5rem; border-radius: 8px; text-align: center; border: 1px solid #e9d5ff;'>
            <div style='font-size: 2.5rem; margin-bottom: 0.5rem;'>💾</div>
            <h4 style='color: #6b46c1; margin-bottom: 0.5rem; font-size: 1rem;'>Simpan</h4>
            <p style='color: #64748b; font-size: 0.85rem; margin: 0;'>Ke Google Sheets</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Contoh/Demo
    with st.expander("📖 Lihat Contoh Penggunaan"):
        st.markdown("""
        ### Contoh Nota yang Didukung:
        - ✅ Nota toko retail (supermarket, minimarket)
        - ✅ Struk restoran/cafe
        - ✅ Invoice toko online
        - ✅ Nota jasa/service
        
        ### Format yang Bisa Diekstrak:
        - Nama barang/produk
        - Jumlah/quantity (qty) - termasuk pecahan seperti 0.5, 1/2
        - Harga satuan
        - Total harga per item
        
        ### 🎯 Confidence Indicator:
        AI akan memberikan indikator visual untuk field yang ragu:
        - **❗ (Merah)**: Confidence < 70% - **Perlu Review**
        - **⚠️ (Kuning)**: Confidence 70-79% - **Cek Ulang**
        - **Tanpa simbol**: Confidence ≥ 80% - Data akurat
        
        Indikator muncul di kolom yang AI ragu, misalnya:
        - ❗ Beras Premium (nama tidak jelas)
        - ⚠️ Minyak Goreng (tulisan blur)
        
        ### 🔧 Fitur Koreksi Otomatis:
        Sistem akan otomatis mendeteksi dan memperbaiki:
        - **Hyper-efficiency**: Harga "20" yang sebenarnya "20.000" atau "20k"
        - **Kuantitas Abstrak**: "1/2" atau "0.5" untuk setengah kilo
        - **Balance Check**: Memastikan qty × harga_satuan = total_harga
        
        ### Yang Diabaikan:
        - Header toko dan alamat
        - Informasi kasir
        - Subtotal, pajak, diskon
        - Total pembayaran akhir
        - Tanda tangan
        """)

# Footer
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("---")
st.markdown("""
    <div style='text-align: center; padding: 1rem; color: #94a3b8;'>
        <p style='margin: 0; font-size: 0.85rem;'>Dibuat dengan ❤️ oleh Tim IT Ozza </p>
    </div>
""", unsafe_allow_html=True)