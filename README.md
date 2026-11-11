# Sistem Informasi Laundry Halilintar

Prototype aplikasi informasi dan pengelolaan pesanan laundry menggunakan Python, Gradio, dan Supabase. Aplikasi dijalankan lokal dari VS Code.

## Fitur

- **Pembeli:** daftar/masuk dengan email dan password, lihat katalog layanan, buat pesanan, dan cek status memakai kode pesanan serta nomor WhatsApp.
- **Admin:** masuk menggunakan akun admin Supabase, melihat ringkasan dan pesanan terbaru, serta mencatat pesanan.
- Ringkasan total pesanan, pesanan aktif, siap diambil, dan pembayaran lunas.
- Katalog layanan dan estimasi pengerjaan.
- Data pelanggan dan pesanan disimpan di Supabase.
- Instruksi pembayaran manual QRIS, transfer BNI, atau tunai.

Aplikasi ini tidak memuat model AI/chatbot. File pelatihan model yang mungkin masih berada di repository tidak digunakan oleh aplikasi.

## Menjalankan aplikasi

Gunakan Python 3.13 dan virtual environment `.venv313`:

```powershell
.\.venv313\Scripts\python.exe -m pip install -r requirements.txt
.\.venv313\Scripts\python.exe app.py
```

Buka URL lokal yang tampil di terminal, biasanya `http://127.0.0.1:7860`.

## Konfigurasi Supabase

Isi `.env` lokal (jangan unggah file ini ke GitHub):

```env
SUPABASE_URL=alamat-project
SUPABASE_KEY=publishable-atau-anon-key
SUPABASE_SECRET_KEY=sb_secret_key-hanya-untuk-backend-lokal
ADMIN_EMAIL=email-admin-yang-diizinkan
```

`SUPABASE_KEY` dipakai untuk katalog dan login Supabase Auth. Agar pesanan tersimpan dan panel admin dapat membaca transaksi, isi `SUPABASE_SECRET_KEY` dengan secret key dari Supabase Dashboard → Project Settings → API Keys. Key ini hanya untuk backend lokal, jangan taruh di kode, browser, atau GitHub. Pembeli mendaftar sendiri dengan email/password; akun dengan email admin yang ditentukan masuk sebagai admin.

## Database

`supabase/schema.sql` mendokumentasikan tabel layanan, FAQ lama, pelanggan, dan pesanan beserta aturan RLS. Katalog dan harga demo yang disediakan:

- Cuci + Setrika Reguler: Rp7.000/kg, estimasi 72 jam.
- Cuci + Lipat: Rp6.000/kg, estimasi 48 jam.
- Express Cuci + Setrika: Rp14.000/kg, estimasi 24 jam.

Harga dan estimasi merupakan data demo dan dapat disesuaikan.

## Pembayaran

QRIS memakai gambar pada `assets/qris-laundry.jpg`. Transfer menggunakan rekening BNI 9800000000 atas nama Adinda Tobing. Pembeli memasukkan nominal sesuai total pesanan; transaksi QRIS/transfer belum diverifikasi otomatis oleh payment gateway. Status pesanan tetap belum lunas sampai pembayaran dikonfirmasi admin.
