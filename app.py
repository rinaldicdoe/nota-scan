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

def process_image_with_gpt4o(image_bytes, mime_type):
    """Mengirim gambar ke OpenAI GPT-4o untuk diekstrak datanya"""
    
    if not client:
        st.error("OpenAI client belum diinisialisasi. Periksa API key Anda.")
        return None
    
    # Encode gambar ke base64
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    
    prompt_text = """
    Analisa gambar nota/invoice ini dengan sangat teliti. Ekstrak SEMUA daftar barang yang dibeli.
    
    PENTING:
    - Abaikan header toko, alamat, nomor telepon, tanggal transaksi
    - Abaikan nama kasir, tanda tangan, footer
    - Abaikan subtotal, pajak (tax/PPN), diskon, atau total pembayaran akhir
    - Ambil HANYA item barang/produk yang dibeli dengan detail berikut:
    
    Untuk setiap item, ambil:
    1. 'nama_barang': Nama produk/item (string)
    2. 'qty': Jumlah/kuantitas barang (integer). Jika tidak ada, asumsikan 1
    3. 'harga_satuan': Harga per unit (integer, tanpa simbol mata uang)
    4. 'total_harga': Total harga untuk item ini (qty × harga_satuan) (integer)
    
    Jika ada harga yang menggunakan format dengan titik/koma (misal: 15.000 atau 15,000), 
    konversi menjadi integer murni (15000).
    
    Output WAJIB format JSON Object murni dengan key 'items' yang berisi array of objects.
    
    Contoh output yang benar:
    {
      "items": [
        {"nama_barang": "Kopi Susu", "qty": 2, "harga_satuan": 15000, "total_harga": 30000},
        {"nama_barang": "Roti Bakar", "qty": 1, "harga_satuan": 12000, "total_harga": 12000}
      ]
    }
    
    Jika tidak ada item yang bisa diekstrak, return: {"items": []}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Lebih murah & cepat, cocok untuk OCR
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}",
                            "detail": "high"  # Gunakan detail tinggi untuk OCR lebih akurat
                        }}
                    ],
                }
            ],
            response_format={"type": "json_object"},
            temperature=0  # 0 untuk konsistensi maksimal
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
    st.markdown("### 📝 Cara Pakai")
    st.markdown("""
    <div style='background: rgba(255,255,255,0.15); padding: 1rem; border-radius: 8px; margin-bottom: 1rem;'>
        <p style='color: white; margin: 0.3rem 0; font-size: 0.9rem;'>1. Upload foto nota</p>
        <p style='color: white; margin: 0.3rem 0; font-size: 0.9rem;'>2. Klik Scan</p>
        <p style='color: white; margin: 0.3rem 0; font-size: 0.9rem;'>3. Review hasil</p>
        <p style='color: white; margin: 0.3rem 0; font-size: 0.9rem;'>4. Simpan ke Sheet</p>
    </div>
    """, unsafe_allow_html=True)
    
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
                    json_data = process_image_with_gpt4o(image_bytes, mime_type)
                    
                    if json_data and 'items' in json_data:
                        items = json_data['items']
                        
                        if len(items) == 0:
                            st.warning("⚠️ Tidak ada item yang berhasil diekstrak. Coba foto/PDF yang lebih jelas.")
                        else:
                            # Convert ke Pandas DataFrame
                            df = pd.DataFrame(items)
                            
                            # Validasi
                            is_valid, msg = validate_dataframe(df)
                            if is_valid:
                                st.session_state.ocr_result_df = df
                                st.session_state.scan_timestamp = datetime.now()
                                st.success(f"✅ Berhasil! Ditemukan {len(df)} item.")
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
                        json_data = process_image_with_gpt4o(img_bytes, img_mime)
                        
                        if json_data and 'items' in json_data:
                            items = json_data['items']
                            # Tambahkan info source file
                            for item in items:
                                item['source_file'] = file.name
                            all_items.extend(items)
                    
                except Exception as e:
                    st.warning(f"⚠️ Error pada {file.name}: {e}")
                
                progress_bar.progress((idx + 1) / len(uploaded_files))
            
            # Combine results
            if all_items:
                df_combined = pd.DataFrame(all_items)
                
                # Reorder columns
                cols_order = ['source_file', 'nama_barang', 'qty', 'harga_satuan', 'total_harga']
                df_combined = df_combined[cols_order]
                
                st.session_state.ocr_result_df = df_combined
                st.session_state.scan_timestamp = datetime.now()
                
                status_text.empty()
                progress_bar.empty()
                st.success(f"✅ Berhasil! Total {len(df_combined)} item dari {len(uploaded_files)} file.")
                st.balloons()
            else:
                status_text.empty()
                progress_bar.empty()
                st.error("❌ Tidak ada item yang berhasil diekstrak dari semua file.")

    # 3. Data Editor (Editable Table)
    if st.session_state.ocr_result_df is not None:
        st.markdown("---")
        st.subheader("📊 Hasil Ekstraksi Data")
        st.info("💡 **Tips:** Klik cell untuk mengedit. Tekan Enter untuk konfirmasi. Klik '+' untuk tambah baris.")
        
        # Widget Data Editor
        column_config = {
            "nama_barang": st.column_config.TextColumn("Nama Barang", width="large", required=True),
            "qty": st.column_config.NumberColumn("Qty", width="small", min_value=1, required=True),
            "harga_satuan": st.column_config.NumberColumn("Harga Satuan (Rp)", width="medium", format="%d", required=True),
            "total_harga": st.column_config.NumberColumn("Total Harga (Rp)", width="medium", format="%d", required=True),
        }
        
        # Tambahkan kolom source_file jika ada (untuk batch mode)
        if 'source_file' in st.session_state.ocr_result_df.columns:
            column_config["source_file"] = st.column_config.TextColumn("File Asal", width="medium")
        
        edited_df = st.data_editor(
            st.session_state.ocr_result_df,
            num_rows="dynamic",  # User bisa tambah/hapus baris
            use_container_width=True,
            column_config=column_config,
            hide_index=False,
        )
        
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
                        # Tambahkan timestamp untuk tracking
                        edited_df_with_timestamp = edited_df.copy()
                        edited_df_with_timestamp.insert(0, 'timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                        
                        # Append ke sheet
                        rows_to_append = edited_df_with_timestamp.values.tolist()
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
        - Jumlah/quantity (qty)
        - Harga satuan
        - Total harga per item
        
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