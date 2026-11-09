import json
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

import gradio as gr
import torch
from dotenv import load_dotenv
from transformers import AutoModelForCausalLM, AutoTokenizer

load_dotenv()
ROOT = Path(__file__).parent
DATA_FILE = ROOT / "data" / "laundry_faq.jsonl"
MODEL_ID = os.getenv("MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct")
ADAPTER_DIR = os.getenv("ADAPTER_DIR", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def make_client(key):
    if not SUPABASE_URL or not key:
        return None
    try:
        from supabase import create_client

        return create_client(SUPABASE_URL, key)
    except Exception as error:
        print(f"Koneksi Supabase gagal ({type(error).__name__}).")
        return None


PUBLIC_DB = make_client(SUPABASE_KEY)
ADMIN_DB = make_client(SUPABASE_SERVICE_ROLE_KEY)


def load_local_faqs():
    with DATA_FILE.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def load_knowledge():
    faqs, services = load_local_faqs(), []
    if PUBLIC_DB:
        try:
            remote_faqs = PUBLIC_DB.table("faqs").select("question, answer").eq("is_active", True).execute().data
            remote_services = (
                PUBLIC_DB.table("services")
                .select("name, description, price_per_kg, estimated_hours, unit_type")
                .eq("is_active", True)
                .execute().data
            )
            faqs = remote_faqs or faqs
            services = remote_services or []
        except Exception as error:
            print(f"Supabase belum dapat dibaca; memakai FAQ lokal ({type(error).__name__}).")
    return faqs, services


def load_model():
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype="auto", device_map="auto")
    if ADAPTER_DIR and Path(ADAPTER_DIR).exists():
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, ADAPTER_DIR)
    model.eval()
    return tokenizer, model


print("Memuat data FAQ dan layanan...")
FAQS, SERVICES = load_knowledge()
print("Memuat Qwen. Unduhan pertama dapat memerlukan waktu.")
tokenizer, model = load_model()


def build_context():
    lines = [f"FAQ: {item['question']} Jawaban: {item['answer']}" for item in FAQS]
    lines.append("Jam buka Laundry Halilintar: setiap hari, Senin sampai Minggu, pukul 07.00–20.00.")
    for item in SERVICES:
        price = item.get("price_per_kg")
        price_text = f"Rp{int(float(price)):,}/kg".replace(",", ".") if price is not None else "harga belum dicantumkan"
        hours = item.get("estimated_hours")
        duration = f"estimasi {hours} jam" if hours is not None else "estimasi belum dicantumkan"
        lines.append(f"Layanan: {item['name']}. {item.get('description', '')} Harga: {price_text}. {duration}.")
    return "\n".join(lines)


def respond(message, history):
    system_text = (
        "Kamu asisten informasi Laundry Halilintar. Jawab singkat, ramah, dalam bahasa Indonesia, "
        "dan gunakan hanya informasi berikut. Jangan mengarang harga atau status pesanan. "
        "Jika informasi tidak tersedia, sarankan menghubungi admin.\n\n" + build_context()
    )
    messages = [{"role": "system", "content": system_text}]
    for item in (history or [])[-6:]:
        if isinstance(item, dict) and item.get("role") in ("user", "assistant"):
            messages.append({"role": item["role"], "content": item.get("content", "")})
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            messages.extend([
                {"role": "user", "content": str(item[0])},
                {"role": "assistant", "content": str(item[1])},
            ])
    messages.append({"role": "user", "content": message})
    inputs = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_tensors="pt", return_dict=True
    ).to(model.device)
    with torch.no_grad():
        output = model.generate(
            **inputs, max_new_tokens=120, do_sample=False, pad_token_id=tokenizer.eos_token_id
        )
    answer = output[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(answer, skip_special_tokens=True).strip()


def format_rupiah(value):
    return "Rp" + f"{int(float(value or 0)):,}".replace(",", ".")


def get_service_rows():
    if ADMIN_DB:
        try:
            return ADMIN_DB.table("services").select("id,name,description,price_per_kg,estimated_hours,is_active").order("id").execute().data
        except Exception:
            pass
    return SERVICES


def service_choices():
    return [f"{row['name']} — {format_rupiah(row.get('price_per_kg'))}/kg" for row in get_service_rows()]


def get_dashboard():
    if not ADMIN_DB:
        return 0, 0, 0, format_rupiah(0), [["—", "Key admin belum diatur", "—", "—", "—", "—"]]
    try:
        rows = ADMIN_DB.table("orders").select("order_code,status,payment_status,total_price,received_at,customers(name),services(name)").order("created_at", desc=True).limit(1000).execute().data
        active = [row for row in rows if row["status"] not in ("Selesai", "Dibatalkan")]
        ready = [row for row in rows if row["status"] == "Siap Diambil"]
        revenue = sum(float(row["total_price"]) for row in rows if row["payment_status"] == "Lunas" and row["status"] != "Dibatalkan")
        table = [[
            row.get("order_code"), (row.get("customers") or {}).get("name", ""),
            (row.get("services") or {}).get("name", ""), row.get("status"),
            row.get("payment_status"), format_rupiah(row.get("total_price")),
        ] for row in rows[:50]]
        if not table:
            table = [["—", "Belum ada pesanan", "Tambahkan pesanan di tab Pesanan", "—", "—", "—"]]
        return len(rows), len(active), len(ready), format_rupiah(revenue), table
    except Exception as error:
        print(f"Tidak dapat memuat data pesanan ({type(error).__name__}). Periksa tabel Supabase dan key admin.")
        return 0, 0, 0, format_rupiah(0), [["—", "Data belum dapat dimuat", "Periksa konfigurasi Supabase", "—", "—", "—"]]


def create_order(name, phone, service_label, weight, payment_method, paid, notes):
    if not ADMIN_DB:
        return "Pengelolaan pesanan belum aktif. Tambahkan SUPABASE_SERVICE_ROLE_KEY ke file .env (jangan dikirim di chat), lalu mulai ulang aplikasi.", *get_dashboard()[:4], get_dashboard()[4], gr.update(choices=service_choices())
    name, phone = (name or "").strip(), (phone or "").strip()
    if not name or not phone:
        return "Isi nama dan nomor WhatsApp pelanggan dulu.", *get_dashboard()[:4], get_dashboard()[4], gr.update(choices=service_choices())
    try:
        kg = float(weight)
        if kg <= 0:
            raise ValueError
    except (TypeError, ValueError):
        snap = get_dashboard()
        return "Berat harus berupa angka lebih dari 0 kg.", *snap[:4], snap[4], gr.update(choices=service_choices())
    services = get_service_rows()
    selected = next((row for row in services if service_label and service_label.startswith(row["name"] + " —")), None)
    if not selected:
        snap = get_dashboard()
        return "Pilih layanan yang tersedia.", *snap[:4], snap[4], gr.update(choices=service_choices())
    price = float(selected.get("price_per_kg") or 0)
    total = round(kg * price)
    try:
        customer_result = ADMIN_DB.table("customers").select("id").eq("phone", phone).limit(1).execute().data
        if customer_result:
            customer_id = customer_result[0]["id"]
            ADMIN_DB.table("customers").update({"name": name}).eq("id", customer_id).execute()
        else:
            customer_id = ADMIN_DB.table("customers").insert({"name": name, "phone": phone}).execute().data[0]["id"]
        now = datetime.now().astimezone()
        order_code = f"LH-{now:%y%m%d}-{secrets.token_hex(2).upper()}"
        duration = int(selected.get("estimated_hours") or 72)
        ADMIN_DB.table("orders").insert({
            "order_code": order_code, "customer_id": customer_id, "service_id": selected["id"],
            "weight_kg": kg, "price_per_kg": price, "total_price": total,
            "status": "Diterima", "payment_method": payment_method if payment_method != "Belum dibayar" else None,
            "payment_status": "Lunas" if paid == "Lunas" else "Belum Lunas",
            "received_at": now.isoformat(), "estimated_ready_at": (now + timedelta(hours=duration)).isoformat(),
            "notes": (notes or "").strip(),
        }).execute()
        snap = get_dashboard()
        return f"Pesanan {order_code} berhasil dicatat. Total {format_rupiah(total)}.", *snap[:4], snap[4], gr.update(choices=service_choices(), value=None)
    except Exception as error:
        snap = get_dashboard()
        return f"Pesanan belum tersimpan ({type(error).__name__}). Periksa koneksi Supabase dan struktur tabel.", *snap[:4], snap[4], gr.update(choices=service_choices())


def update_order(order_code, status, payment_status, payment_method):
    if not ADMIN_DB:
        snap = get_dashboard()
        return "Key admin belum diatur.", *snap
    if not order_code:
        snap = get_dashboard()
        return "Pilih kode pesanan terlebih dahulu.", *snap
    try:
        values = {"status": status, "payment_status": payment_status, "updated_at": datetime.now().astimezone().isoformat()}
        values["payment_method"] = payment_method if payment_method != "Belum dibayar" else None
        ADMIN_DB.table("orders").update(values).eq("order_code", order_code).execute()
        snap = get_dashboard()
        return f"Pesanan {order_code} berhasil diperbarui.", *snap
    except Exception as error:
        snap = get_dashboard()
        return f"Gagal memperbarui pesanan ({type(error).__name__}).", *snap


def refresh_dashboard():
    return get_dashboard()


def ask_chat(message, history):
    clean = (message or "").strip()
    if not clean:
        return history or [], ""
    updated = list(history or [])
    updated.extend([{"role": "user", "content": clean}, {"role": "assistant", "content": respond(clean, history or [])}])
    return updated, ""


def initial_chat():
    return [{"role": "assistant", "content": "Halo! Aku Asisten Laundry Halilintar. Tanyakan harga, layanan, atau jam buka kami."}]


CSS = """
html, body, #root, gradio-app, .gradio-container { background:#f4f7f4 !important; color-scheme:light !important; }
body { margin:0 !important; }
.gradio-container { width:100% !important; max-width:none !important; margin:0 auto !important; padding:12px clamp(18px, 4vw, 64px) 48px !important; box-sizing:border-box !important; color:#19382c !important; }
main { width:100% !important; max-width:1420px !important; margin:0 auto !important; }
footer { display:none !important; }
#header { display:flex; align-items:center; justify-content:space-between; gap:20px; padding:19px 24px; background:#fff; border:1px solid #e4ebe6; border-radius:20px; margin:4px 0 22px; box-shadow:0 8px 28px rgba(28,62,44,.055); }
#brand-wrap { display:flex; align-items:center; gap:13px; }
#brand-mark { width:46px; height:46px; display:grid; place-items:center; background:#e5f3e9; color:#247047; border-radius:15px; font-size:22px; }
#brand { font-weight:800; font-size:20px; line-height:1.2; color:#17563b; }
#subbrand { color:#718278; font-size:12px; margin-top:4px; }
#header-meta { display:flex; align-items:center; gap:8px; color:#52685b; font-size:12px; }
.open-chip { padding:9px 13px; border:1px solid #dce9df; background:#f8fcf9; border-radius:999px; white-space:nowrap; }
.page-intro { margin:8px 2px 16px; }
.page-intro h2 { font-size:24px; color:#193e2e; margin:0 0 5px; }
.page-intro p { color:#718278; margin:0; }
button[role="tab"] { border-radius:12px 12px 0 0 !important; padding:12px 18px !important; font-weight:650 !important; color:#60756a !important; }
button[role="tab"][aria-selected="true"] { color:#17683f !important; border-bottom:3px solid #278653 !important; background:#fff !important; }
[data-testid="tabitem"] { padding-top:19px !important; }
#metric-total, #metric-active, #metric-ready, #metric-revenue { background:#fff !important; border:1px solid #e1eae4 !important; border-radius:17px !important; padding:14px 16px !important; box-shadow:0 5px 18px rgba(28,62,44,.045) !important; }
#metric-total label, #metric-active label, #metric-ready label, #metric-revenue label { color:#718278 !important; font-size:12px !important; font-weight:600 !important; }
#metric-total input, #metric-active input, #metric-ready input, #metric-revenue input { color:#17683f !important; background:#fff !important; border:0 !important; font-size:26px !important; font-weight:800 !important; padding-left:0 !important; }
#load-summary, #create-order, #update-order { border-radius:12px !important; min-height:44px; font-weight:700 !important; }
button.primary { background:#19734a !important; color:white !important; border-color:#19734a !important; }
button.primary:hover { background:#145c3b !important; }
#recent-orders { overflow:hidden; background:#fff !important; border:1px solid #e1eae4 !important; border-radius:16px !important; }
table, [data-testid="table"] { background:#fff !important; color:#244034 !important; }
thead, th { background:#edf4ef !important; color:#355846 !important; font-weight:700 !important; }
td, th { border-color:#e5ece7 !important; padding:12px 14px !important; }
input, textarea, select { background:#fff !important; color:#20392e !important; border-color:#dce7df !important; border-radius:11px !important; }
.block, [data-testid="block"] { border-color:#e4ebe6 !important; }
.prose, .markdown { color:#42594c !important; }
#setup-notice { padding:12px 16px; background:#fff7e8; color:#765615; border:1px solid #f0dfb8; border-radius:13px; }
@media (max-width:760px) {
 .gradio-container { padding:8px 12px 28px !important; }
 #header { padding:15px; border-radius:16px; }
 #header-meta { display:none; }
 .page-intro h2 { font-size:21px; }
 button[role="tab"] { padding:10px 11px !important; font-size:12px !important; }
 #metric-total, #metric-active, #metric-ready, #metric-revenue { padding:10px !important; }
}
"""

with gr.Blocks(title="Laundry Halilintar") as demo:
    gr.HTML("<div id='header'><div id='brand-wrap'><div id='brand-mark'>✦</div><div><div id='brand'>Laundry Halilintar</div><div id='subbrand'>Sistem informasi operasional laundry</div></div></div><div id='header-meta'><span class='open-chip'>● Buka setiap hari</span><span class='open-chip'>07.00—20.00</span></div></div>")
    with gr.Tabs():
        with gr.Tab("Ringkasan"):
            gr.Markdown("<div class='page-intro'><h2>Ringkasan operasional</h2><p>Pantau pesanan hari ini dan progres cucian pelanggan.</p></div>")
            if not ADMIN_DB:
                gr.Markdown("<div id='setup-notice'>Data ringkasan masih kosong karena key admin Supabase belum diisi di file .env lokal.</div>")
            with gr.Row(equal_height=True):
                total_card = gr.Number(label="Total pesanan", value=0, interactive=False, elem_id="metric-total")
                active_card = gr.Number(label="Sedang berjalan", value=0, interactive=False, elem_id="metric-active")
                ready_card = gr.Number(label="Siap diambil", value=0, interactive=False, elem_id="metric-ready")
                revenue_card = gr.Textbox(label="Pembayaran lunas", value="Rp0", interactive=False, elem_id="metric-revenue")
            refresh_button = gr.Button("↻  Muat ulang ringkasan", elem_id="load-summary")
            gr.Markdown("### Pesanan terbaru")
            orders_table = gr.Dataframe(headers=["Kode", "Pelanggan", "Layanan", "Status", "Pembayaran", "Total"], interactive=False, wrap=True, elem_id="recent-orders")
            refresh_button.click(refresh_dashboard, outputs=[total_card, active_card, ready_card, revenue_card, orders_table])

        with gr.Tab("Pesanan"):
            gr.Markdown("### Catat pesanan baru\nKode pesanan dibuat otomatis. Harga disimpan sebagai snapshot saat transaksi dibuat.")
            if not ADMIN_DB:
                gr.Markdown("**Pengelolaan pesanan belum aktif.** Tambahkan `SUPABASE_SERVICE_ROLE_KEY` ke `.env` dari Supabase Dashboard → Project Settings → API Keys → Legacy API Keys → `service_role`, lalu mulai ulang aplikasi. Simpan key hanya di `.env` lokal; jangan kirim lewat chat atau unggah ke GitHub.")
            with gr.Row():
                with gr.Column():
                    customer_name = gr.Textbox(label="Nama pelanggan")
                    customer_phone = gr.Textbox(label="Nomor WhatsApp", placeholder="08xxxxxxxxxx")
                    service_select = gr.Dropdown(choices=service_choices(), label="Layanan")
                    weight_input = gr.Number(label="Berat (kg)", minimum=0.1, value=1, precision=2)
                with gr.Column():
                    payment_select = gr.Dropdown(["Belum dibayar", "Tunai", "QRIS", "Transfer Bank"], value="Belum dibayar", label="Metode pembayaran")
                    paid_select = gr.Radio(["Belum Lunas", "Lunas"], value="Belum Lunas", label="Status pembayaran")
                    notes_input = gr.Textbox(label="Catatan cucian", lines=3, placeholder="Contoh: pakaian putih dipisah")
                    create_button = gr.Button("Simpan pesanan", variant="primary", elem_id="create-order")
            order_notice = gr.Markdown()
            gr.Markdown("### Perbarui status pesanan")
            with gr.Row():
                update_code = gr.Textbox(label="Kode pesanan")
                update_status_select = gr.Dropdown(["Diterima", "Diproses", "Siap Diambil", "Selesai", "Dibatalkan"], value="Diproses", label="Status pesanan")
            with gr.Row():
                update_paid_select = gr.Dropdown(["Belum Lunas", "Lunas"], value="Belum Lunas", label="Status pembayaran")
                update_payment_select = gr.Dropdown(["Belum dibayar", "Tunai", "QRIS", "Transfer Bank"], value="Belum dibayar", label="Metode pembayaran")
            update_button = gr.Button("Perbarui pesanan", elem_id="update-order")
            update_notice = gr.Markdown()

        with gr.Tab("Layanan"):
            gr.Markdown("### Daftar layanan demo\nHarga di bawah adalah harga awal yang bisa disesuaikan oleh pemilik usaha.")
            service_table = gr.Dataframe(headers=["Layanan", "Deskripsi", "Harga/kg", "Estimasi (jam)"], interactive=False, value=[
                [row.get("name"), row.get("description"), format_rupiah(row.get("price_per_kg")), row.get("estimated_hours")]
                for row in get_service_rows()
            ])

        with gr.Tab("Asisten AI"):
            gr.Markdown("### Asisten informasi Laundry Halilintar\nJawaban menggunakan Qwen dan informasi FAQ/layanan yang tersedia.")
            chat = gr.Chatbot(value=initial_chat(), height=430, show_label=False)
            with gr.Row():
                chat_input = gr.Textbox(placeholder="Tanyakan harga, layanan, atau jam buka...", show_label=False, scale=8)
                chat_send = gr.Button("Kirim", variant="primary", scale=1)
            chat_clear = gr.Button("Hapus obrolan", size="sm")
            chat_input.submit(ask_chat, [chat_input, chat], [chat, chat_input])
            chat_send.click(ask_chat, [chat_input, chat], [chat, chat_input])
            chat_clear.click(lambda: (initial_chat(), ""), outputs=[chat, chat_input])

    create_button.click(
        create_order,
        [customer_name, customer_phone, service_select, weight_input, payment_select, paid_select, notes_input],
        [order_notice, total_card, active_card, ready_card, revenue_card, orders_table, service_select],
    )
    update_button.click(
        update_order,
        [update_code, update_status_select, update_paid_select, update_payment_select],
        [update_notice, total_card, active_card, ready_card, revenue_card, orders_table],
    )
    demo.load(refresh_dashboard, outputs=[total_card, active_card, ready_card, revenue_card, orders_table])

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(primary_hue="green", secondary_hue="emerald", neutral_hue="slate"), css=CSS)

