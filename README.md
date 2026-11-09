# Chatbot Informasi Laundry

Prototype chatbot laundry dengan Qwen, Gradio, Supabase, dan adapter LoRA. Kode ini dapat dijalankan dari VS Code atau Google Colab.

## Isi proyek

- `app.py`: chatbot Gradio yang membaca FAQ dan layanan dari Supabase. Jika Supabase belum diatur, aplikasi memakai FAQ lokal.
- `data/laundry_faq.jsonl`: contoh data latihan; ubah jawabannya sesuai laundry yang dipilih.
- `train_lora.py`: adaptasi model Qwen pretrained dengan LoRA.
- `supabase/schema.sql`: tabel `services` dan `faqs` beserta kebijakan baca publik.

Prototype ini menjawab informasi layanan. Belum menerima transaksi atau mengecek status pesanan.

## Siapkan database Supabase

1. Buka proyek Supabase, pilih **SQL Editor → New query**.
2. Salin dan jalankan isi `supabase/schema.sql`.
3. Buka **Project Settings → API**, salin Project URL dan publishable/anon key ke `.env`.
4. Sesuaikan FAQ dan isi daftar layanan dengan informasi yang benar.
5. Jangan masukkan `service_role` key ke aplikasi atau GitHub.

## Jalankan dari VS Code

Pasang Python 3.10 atau lebih baru, buka folder proyek di VS Code, lalu jalankan di Terminal:

```bash
python -m venv .venv
```

Aktifkan environment: PowerShell Windows `.venv\\Scripts\\Activate.ps1`, atau macOS/Linux `source .venv/bin/activate`.

```bash
pip install -r requirements.txt
```

Salin `.env.example` menjadi `.env`, isi kredensial Supabase (boleh dikosongkan untuk memakai FAQ lokal), lalu:

```bash
python app.py
```

Buka alamat Gradio yang tampil di terminal, biasanya `http://127.0.0.1:7860`. Model Qwen diunduh saat pertama kali dijalankan. GPU mempercepat proses; CPU bisa lebih lambat.

## Adaptasi LoRA

Untuk pemula, jalankan tahap ini di Google Colab dengan runtime GPU. Unggah folder proyek atau clone repo, lalu:

```bash
pip install -r requirements.txt
python train_lora.py
```

Adapter disimpan di `adapter-laundry/`. Isi `ADAPTER_DIR=adapter-laundry` di `.env`, lalu jalankan ulang aplikasi. Jika adapter belum dibuat, aplikasi memakai model dasar.

Untuk evaluasi, siapkan pertanyaan uji baru dan bandingkan model dasar dengan model LoRA dari sisi ketepatan, kesesuaian dengan informasi laundry, dan jawaban yang mengarang. Dataset contoh kecil ini hanya untuk demo awal.

