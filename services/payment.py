import logging
from services.database import DatabaseService

class PaymentService:
    def __init__(self, db: DatabaseService):
        self.db = db
        # Midtrans dinonaktifkan sementara agar tidak crash di Railway
        self.snap = None 

    async def create_transaction(self, user_id: int, item_type: str):
        """
        Versi Manual: Mengambil info harga dan mengarahkan user ke sistem manual.
        """
        
        # --- DAFTAR HARGA RESMI PICKME (JANGAN DIUBAH) ---
        prices = {
            # Sultan VIP
            "vip_1_week": 10000,         
            "vip_1_month": 30000,        
            "vip_3_month": 75000,        
            
            # Sultan VIP+
            "vip_plus_1_week": 30000,    
            "vip_plus_1_month": 100000,  
            "vip_plus_3_month": 250000,  
            
            # Saldo Extra Feed (Eceran)
            "extra_10": 10000,           
            "extra_30": 30000,           
            "extra_50": 50000,           
            
            # Fitur Lainnya
            "talent_reg": 10000,         
            "boost_1": 5000,             
            "boost_5": 20000,            
        }

        amount = prices.get(item_type, 0)
        
        if amount == 0:
            logging.error(f"⚠️ Item tidak valid: {item_type}")
            return None, "Paket tidak ditemukan."

        # Logging untuk memantau paket apa yang paling sering diklik user
        logging.info(f"ℹ️ User {user_id} mengecek paket {item_type} (Mode Manual)")
        
        # Mengembalikan None untuk URL agar Pricing Handler tahu ini mode manual
        return None, item_type
