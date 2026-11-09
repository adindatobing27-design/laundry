# Sistem Informasi Laundry Halilintar

Prototype ini menggabungkan pencatatan pesanan laundry di Supabase dengan chatbot informasi berbasis Qwen. Aplikasi dijalankan lokal dari VS Code menggunakan Gradio.

## Fitur

- **Pembeli:** lihat katalog dan estimasi, buat pesanan, cek status memakai kode pesanan + nomor WhatsApp, dan tanya chatbot.
- **Admin:** login PIN, lihat ringkasan, catat pesanan di kasir, dan perbarui status/pembayaran.
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
SUPABASE_SERVICE_ROLE_KEY=service-role-key-hanya-untuk-backend-lokal
ADMIN_PIN=buat-pin-admin-sendiri
MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct
ADAPTER_DIR=
```

`SUPABASE_KEY` digunakan untuk membaca FAQ dan layanan publik. Agar pesanan pembeli, dashboard admin, dan perubahan status berfungsi, isi `SUPABASE_SERVICE_ROLE_KEY` dari Supabase Dashboard → Project Settings → API Keys → Legacy API Keys → `service_role`. Atur `ADMIN_PIN` dengan PIN pilihan sendiri. Simpan keduanya hanya di `.env` lokal. Jangan masukkan key tersebut ke kode, GitHub, chatbot, atau browser. Key admin dapat melewati RLS; prototype ini hanya dijalankan lokal dan tidak boleh dipublikasikan ke internet dengan key tersebut. Untuk aplikasi yang dihosting publik, ganti login PIN lokal dengan Supabase Auth dan kebijakan admin yang sesuai.

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

