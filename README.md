# Prototype AI Informasi Laundry

Prototype ini memakai model Qwen pretrained, dataset FAQ laundry, adaptasi LoRA, Supabase untuk menyimpan informasi layanan/FAQ, dan Gradio untuk antarmuka chatbot.

## Isi folder

- `app.py` — chatbot yang menjawab dari FAQ dan layanan Supabase.
- `data/laundry_faq.jsonl` — dataset latihan buatan untuk demo. Ganti atau tambah dengan informasi laundry yang benar.
- `data/evaluation_questions.jsonl` — pertanyaan uji yang tidak dipakai saat pelatihan.
- `train_lora.py` — melatih adapter LoRA; loss hanya dihitung pada jawaban asisten.
- `evaluate.py` — membuat perbandingan jawaban model dasar dan model LoRA dalam CSV.
- `supabase/schema.sql` — tabel `services` dan `faqs`, kebijakan RLS, dan izin baca untuk chatbot.

## Mulai dari VS Code

### 1. Siapkan Python

Gunakan Python 3.11 atau lebih baru. Buka folder proyek ini di VS Code, lalu buka **Terminal → New Terminal**.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Jika PowerShell menolak aktivasi environment, jalankan aplikasi dengan `.venv\Scripts\python.exe app.py` setelah library terpasang.

### 2. Isi informasi laundry

File `.env` lokal sudah disiapkan untuk koneksi ke Supabase. Jangan unggah file ini ke GitHub.

Di Supabase buka **Table Editor → services → Insert row**. Isi nama layanan, deskripsi, harga per kilogram, dan estimasi jam sesuai laundry yang sebenarnya. Tabel FAQ sudah memiliki empat contoh; edit atau tambah FAQ yang sesuai. Jangan gunakan harga contoh sebelum diperiksa.

### 3. Jalankan chatbot model dasar

```powershell
python app.py
```

Buka URL lokal yang muncul di terminal (biasanya `http://127.0.0.1:7860`). Pertama kali jalan, Qwen diunduh sehingga perlu internet dan waktu tunggu. Tanpa adapter, aplikasi menggunakan model pretrained dasar.

## Adaptasi model dengan Google Colab

Gunakan Colab dengan runtime GPU untuk pelatihan. Di Colab jalankan sel berikut:

```python
!git clone https://github.com/adindatobing27-design/laundry.git
%cd laundry
!pip install -r requirements.txt
!python train_lora.py
```

Setelah pelatihan, unduh adapter dari Colab:

```python
from google.colab import files
files.download("adapter-laundry.zip")
```

Ekstrak ZIP ke folder proyek VS Code sehingga terdapat folder `adapter-laundry` berisi file adapter. Lalu ubah baris `ADAPTER_DIR=` di `.env` menjadi `ADAPTER_DIR=adapter-laundry`, kemudian jalankan ulang `python app.py`.

## Bandingkan model sebelum dan sesudah LoRA

Jalankan dari root folder proyek di Colab setelah adapter selesai dibuat:

```python
!python evaluate.py
```

Script menghasilkan `hasil_evaluasi.csv` dengan pertanyaan, jawaban acuan, jawaban model dasar, dan jawaban LoRA. Bandingkan secara manual: ketepatan informasi, kesesuaian jawaban, dan apakah model mengarang. Isi kolom `penilaian_manual`; jangan menyimpulkan LoRA lebih baik tanpa melihat hasil. Unduh hasilnya dengan:

```python
from google.colab import files
files.download("hasil_evaluasi.csv")
```

Dataset contoh masih kecil dan bersifat sintetis. Tambahkan pertanyaan nyata dengan jawaban yang sudah diverifikasi sebelum menjadikannya bahan kesimpulan presentasi. Jangan masukkan data pribadi pelanggan ke dataset.

## Batas prototype

Prototype ini menjawab pertanyaan umum tentang layanan laundry. Belum membuat transaksi, menyimpan data pelanggan, atau membaca status pesanan. Harga dan status pesanan tidak boleh ditebak oleh chatbot; arahkan pelanggan ke admin jika data belum tersedia.

