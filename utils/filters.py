import re

# 1. DAFTAR KATA TERLARANG (Blacklist)
# Kelompokkan berdasarkan kategori agar mudah dikelola
SARA_POLITIK = ["pki", "komunis", "khilafah", "rasis", "papua merdeka"]
PORN_VCS = ["vcs", "open bo", "bo", "vcs sange", "pap tt", "pap memek", "bokep", "porn", "p0rn", "sange"]
JUDI_SLOT = ["slot", "gacor", "jp paus", "judi", "zeus", "olympus", "mahjong ways"]
KASAR_TOXIC = ["anjing", "bangsat", "tolol", "goblok", "kontol", "memek", "jembut", "peler"]

# Gabungkan semua ke dalam satu list besar
BANNED_WORDS = SARA_POLITIK + PORN_VCS + JUDI_SLOT + KASAR_TOXIC

def is_content_safe(text: str) -> bool:
    """
    Mengecek keamanan teks menggunakan Blacklist & Normalisasi teks sederhana.
    Return True jika AMAN.
    Return False jika MENGANDUNG KATA TERLARANG.
    """
    if not text:
        return True
    
    # --- STEP 1: NORMALISASI TEKS ---
    # Ubah ke huruf kecil
    clean_text = text.lower()
    
    # Ganti angka yang sering digunakan sebagai huruf (Leetspeak)
    # Contoh: '5lot' jadi 'slot', 'b0kep' jadi 'bokep'
    replacements = {
        '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't', '8': 'b'
    }
    for num, char in replacements.items():
        clean_text = clean_text.replace(num, char)
    
    # Hapus simbol-simbol aneh agar tidak mengecoh filter (misal: 's.l.o.t')
    clean_text = re.sub(r'[^a-zA-Z\s]', '', clean_text)

    # --- STEP 2: PENGECEKAN KATA ---
    # Cek setiap kata terlarang di dalam teks yang sudah dibersihkan
    for word in BANNED_WORDS:
        # Gunakan regex untuk mencari kata yang berdiri sendiri (mencegah false positive)
        # Contoh: Tidak akan memblokir kata 'KOSAN' hanya karena mengandung 'AN'
        pattern = r'\b' + re.escape(word) + r'\b'
        if re.search(pattern, clean_text):
            return False
            
    return True

def get_banned_reason(text: str) -> str:
    """
    Opsional: Memberitahu user kategori apa yang mereka langgar (tanpa menyebutkan katanya).
    """
    clean_text = text.lower()
    if any(w in clean_text for w in SARA_POLITIK): return "SARA / Politik"
    if any(w in clean_text for w in PORN_VCS): return "Konten Dewasa / VCS"
    if any(w in clean_text for w in JUDI_SLOT): return "Promosi Judi / Slot"
    if any(w in clean_text for w in KASAR_TOXIC): return "Kata-kata Kasar"
    return "Pelanggaran Aturan"
    
