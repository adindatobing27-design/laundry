# Sistem Informasi Laundry Halilintar

Prototype ini menggabungkan pencatatan pesanan laundry di Supabase dengan chatbot informasi berbasis Qwen. Aplikasi dijalankan lokal dari VS Code menggunakan Gradio.

## Fitur

- **Pembeli:** lihat katalog dan estimasi, buat pesanan, cek status memakai kode pesanan + nomor WhatsApp, dan tanya chatbot. Login Google belum diaktifkan.
- **Admin:** masuk dengan email/password Supabase Auth yang emailnya diizinkan pada `ADMIN_EMAIL`, lihat ringkasan, catat pesanan di kasir, dan perbarui status/pembayaran.
- Ringkasan total pesanan, pesanan aktif, siap diambil, dan nilai transaksi lunas.
- Pencatatan pelanggan dan pesanan, nomor pesanan otomatis, catatan cucian, status pengerjaan, dan pembayaran.
- Daftar layanan kiloan dan estimasi pengerjaan.
- Chatbot FAQ menggunakan model pretrained Qwen; tidak membuat model dari awal.
- Data pelanggan dan pesanan dilindungi RLS dan hanya diakses backend admin.

## Menjalankan aplikasi

Gunakan Python 3.13 dan virtual environment `.venv313` seperti yang sudah disiapkan di komputer pemilik proyek.

```powershell
.\.venv313\Scripts\python.exe app.py
```

Buka URL lokal yang tampil di terminal, biasanya `http://127.0.0.1:7860`. Pertama kali menjalankan aplikasi, Qwen perlu diunduh.

## Konfigurasi Supabase

Isi `.env` lokal (jangan unggah file ini ke GitHub):

```env
SUPABASE_URL=alamat-project
SUPABASE_KEY=publishable-atau-anon-key
SUPABASE_SECRET_KEY=sb_secret_key-hanya-untuk-backend-lokal
ADMIN_EMAIL=email-admin-yang-diizinkan
MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct
ADAPTER_DIR=
```

`SUPABASE_KEY` adalah publishable key untuk membaca FAQ dan layanan serta melakukan login Supabase Auth. Agar pesanan tersimpan dan panel admin bisa membaca transaksi, isi `SUPABASE_SECRET_KEY` dari Supabase Dashboard → Project Settings → API Keys → Secret keys (`sb_secret_...`). Jika project lama belum memiliki secret key, key `service_role` lama dapat diisi pada `SUPABASE_SERVICE_ROLE_KEY`. Jangan masukkan key server ke kode, GitHub, chatbot, atau browser. Key server dapat melewati RLS; prototype ini dijalankan lokal saja dan tidak boleh dipublikasikan ke internet dengan key tersebut. Admin masuk memakai akun Supabase Auth dan emailnya harus cocok dengan `ADMIN_EMAIL`. Buat/reset password akun admin lewat Supabase Dashboard → Authentication → Users. Login Google pembeli memerlukan Google OAuth Client ID/Secret di Google Cloud Console dan provider Google yang diaktifkan pada Supabase Auth.

### Menyiapkan login Google dan admin

1. Di Google Cloud Console, buat **OAuth Client ID** dengan tipe **Web application**. Pada bagian **Authorized redirect URIs**, masukkan URL callback yang ditampilkan Supabase di Authentication → Sign In / Providers → Google. Untuk project ini biasanya bentuknya `https://rtdkbaamgqvxoygahthy.supabase.co/auth/v1/callback`.
2. Salin Client ID dan Client Secret dari Google Cloud Console, lalu masukkan langsung ke kolom provider Google di Supabase Dashboard. Jangan taruh Client Secret di `.env` atau GitHub.
3. Di Supabase Authentication → URL Configuration → Redirect URLs, izinkan `http://127.0.0.1:7860/**` dan `http://localhost:7860/**` untuk login lokal.
4. Buat user admin di Supabase Dashboard → Authentication → Users. Gunakan email yang sama dengan `ADMIN_EMAIL`; set password di Dashboard. Aplikasi hanya menerima email admin yang sudah ditentukan itu.
5. Ganti isi `SUPABASE_SECRET_KEY` di `.env` lokal dengan Secret key `sb_secret_...` dari Project Settings → API Keys. Jangan pernah menaruh publishable key di `SUPABASE_SECRET_KEY`.
6. Mulai ulang aplikasi. Login Google membuat akun pembeli Supabase Auth saat mereka pertama kali masuk (jika pendaftaran user baru diizinkan). Pesanan baru ditautkan ke ID akun tersebut.

## Database

`supabase/schema.sql` mendokumentasikan tabel `services`, `faqs`, `customers`, dan `orders`, aturan RLS, serta layanan dan FAQ demo. Skema awal sudah diterapkan pada project Supabase Laundry.

Harga demo saat ini:

- Cuci + Setrika Reguler: Rp7.000/kg, estimasi 72 jam.
- Cuci + Lipat: Rp6.000/kg, estimasi 48 jam.
- Express Cuci + Setrika: Rp14.000/kg, estimasi 24 jam.

Harga dan estimasi adalah data demo yang dapat diubah setelah dibandingkan dengan harga usaha sebenarnya.

## Adaptasi model untuk tugas AI

Chatbot memakai model pretrained `Qwen/Qwen2.5-0.5B-Instruct` dan konteks FAQ/layanan Supabase. Tahap pertama menggunakan adaptasi konteks (RAG sederhana), bukan fine-tuning. FAQ bukan data transaksi. Data pesanan dan nomor pelanggan tidak dimasukkan ke dataset pelatihan.

Jika ingin menjalankan LoRA setelah dataset pertanyaan-jawaban ditambah dan ditinjau, gunakan `data/laundry_faq.jsonl`, `train_lora.py`, dan `evaluate.py`. Latih di Google Colab dengan GPU, simpan adapter ke `adapter-laundry`, lalu atur `ADAPTER_DIR=adapter-laundry` pada `.env`. Evaluasi pertanyaan terpisah sebelum menyimpulkan adapter lebih baik daripada model dasar.

Dataset sekarang kecil dan sintetis; jawaban layanan perlu diverifikasi sebelum demo publik atau dipakai sebagai informasi usaha nyata.

