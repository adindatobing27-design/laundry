import json
import html
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
ADMIN_PIN = os.getenv("ADMIN_PIN", "").strip()


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


def create_order_record(name, phone, service_label, weight, payment_method, paid, notes=""):
    if not ADMIN_DB:
        return None, None, "Sambungan admin Supabase belum disiapkan."
    name, phone = (name or "").strip(), (phone or "").strip()
    if not name or not phone:
        return None, None, "Isi nama dan nomor WhatsApp pelanggan dulu."
    try:
        kg = float(weight)
        if kg <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return None, None, "Berat harus berupa angka lebih dari 0 kg."
    services = get_service_rows()
    selected = next((row for row in services if service_label and service_label.startswith(row["name"] + " —")), None)
    if not selected:
        return None, None, "Pilih layanan yang tersedia."
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
        order_code = f"LH-{now:%y%m%d}-{secrets.token_hex(4).upper()}"
        duration = int(selected.get("estimated_hours") or 72)
        ADMIN_DB.table("orders").insert({
            "order_code": order_code, "customer_id": customer_id, "service_id": selected["id"],
            "weight_kg": kg, "price_per_kg": price, "total_price": total,
            "status": "Diterima", "payment_method": payment_method if payment_method != "Belum dibayar" else None,
            "payment_status": "Lunas" if paid == "Lunas" else "Belum Lunas",
            "received_at": now.isoformat(), "estimated_ready_at": (now + timedelta(hours=duration)).isoformat(),
            "notes": (notes or "").strip(),
        }).execute()
        return order_code, total, None
    except Exception as error:
        return None, None, f"Pesanan belum tersimpan ({type(error).__name__}). Periksa koneksi Supabase dan struktur tabel."


def create_order(name, phone, service_label, weight, payment_method, paid, notes, is_admin):
    if not is_admin:
        snap = (0, 0, 0, format_rupiah(0), [])
        return "Silakan login admin terlebih dahulu.", *snap[:4], snap[4], gr.update(choices=service_choices())
    code, total, error = create_order_record(name, phone, service_label, weight, payment_method, paid, notes)
    snap = get_dashboard()
    if error:
        return error, *snap[:4], snap[4], gr.update(choices=service_choices())
    return f"Pesanan {code} berhasil dicatat. Total {format_rupiah(total)}.", *snap[:4], snap[4], gr.update(choices=service_choices(), value=None)


def create_buyer_order(name, phone, service_label, weight, payment_method, notes):
    code, total, error = create_order_record(name, phone, service_label, weight, payment_method, "Belum Lunas", notes)
    if error:
        return error
    return f"Pesanan berhasil dikirim! Simpan kode **{code}** untuk mengecek status. Perkiraan total {format_rupiah(total)}. Pembayaran dapat diselesaikan saat proses pesanan."


def track_buyer_order(order_code, phone):
    if not ADMIN_DB:
        return "Pelacakan belum siap. Koneksi admin Supabase perlu diatur terlebih dahulu."
    code, phone = (order_code or "").strip().upper(), (phone or "").strip()
    if not code or not phone:
        return "Masukkan kode pesanan dan nomor WhatsApp yang digunakan saat memesan."
    try:
        rows = (ADMIN_DB.table("orders").select("order_code,status,payment_status,total_price,estimated_ready_at,customers(phone),services(name)").eq("order_code", code).limit(1).execute().data)
        if not rows or (rows[0].get("customers") or {}).get("phone") != phone:
            return "Pesanan tidak ditemukan. Periksa kembali kode dan nomor WhatsApp."
        row = rows[0]
        ready = datetime.fromisoformat(row["estimated_ready_at"].replace("Z", "+00:00")).astimezone().strftime("%d %b %Y, %H.%M")
        service = (row.get("services") or {}).get("name", "Layanan laundry")
        return f"**{row['order_code']} · {service}**\n\nStatus: **{row['status']}**  \nPembayaran: **{row['payment_status']}**  \nTotal: **{format_rupiah(row['total_price'])}**  \nPerkiraan selesai: **{ready}**"
    except Exception as error:
        return f"Status belum dapat dimuat ({type(error).__name__}). Coba lagi sebentar."


def update_order(order_code, status, payment_status, payment_method, is_admin):
    if not is_admin:
        snap = (0, 0, 0, format_rupiah(0), [])
        return "Silakan login admin terlebih dahulu.", *snap
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


def login_admin(pin):
    if not ADMIN_DB:
        return "Koneksi admin Supabase belum siap. Isi service role key di .env lokal.", False, gr.update(visible=True), gr.update(visible=False), 0, 0, 0, format_rupiah(0), []
    if not ADMIN_PIN:
        return "PIN admin belum diatur. Isi ADMIN_PIN di .env lokal lalu mulai ulang aplikasi.", False, gr.update(visible=True), gr.update(visible=False), 0, 0, 0, format_rupiah(0), []
    if not secrets.compare_digest(str(pin or ""), ADMIN_PIN):
        return "PIN salah. Coba lagi.", False, gr.update(visible=True), gr.update(visible=False), 0, 0, 0, format_rupiah(0), []
    return "Login berhasil.", True, gr.update(visible=False), gr.update(visible=True), *get_dashboard()


def logout_admin():
    return "Silakan login untuk masuk kembali.", False, gr.update(visible=True), gr.update(visible=False), 0, 0, 0, format_rupiah(0), []


def refresh_dashboard_for_admin(is_admin):
    return get_dashboard() if is_admin else (0, 0, 0, format_rupiah(0), [])


def ask_chat(message, history):
    clean = (message or "").strip()
    if not clean:
        return history or [], ""
    updated = list(history or [])
    updated.extend([{"role": "user", "content": clean}, {"role": "assistant", "content": respond(clean, history or [])}])
    return updated, ""


def initial_chat():
    return [{"role": "assistant", "content": "Halo! Aku Asisten Laundry Halilintar. Tanyakan harga, layanan, atau jam buka kami."}]



def service_cards_markup():
    cards = []
    for item in SERVICES:
        name = html.escape(str(item.get("name", "Layanan Laundry")))
        description = html.escape(str(item.get("description", "Layanan laundry bersih dan rapi.")))
        price = format_rupiah(item.get("price_per_kg"))
        hours = int(item.get("estimated_hours") or 72)
        days = max(1, round(hours / 24))
        cards.append(
            f"<article class='service-card'><div class='service-icon'>✧</div>"
            f"<h3>{name}</h3><p>{description}</p><strong>{price}<small> / kg</small></strong>"
            f"<div class='service-time'>Estimasi {days} hari</div></article>"
        )
    if not cards:
        cards.append("<article class='service-card'><div class='service-icon'>✧</div><h3>Cuci + Setrika Reguler</h3><p>Cuci, kering, setrika, dan lipat.</p><strong>Rp7.000<small> / kg</small></strong><div class='service-time'>Estimasi 3 hari</div></article>")
    return "<div class='service-grid'>" + "".join(cards) + "</div>"


MACHINE_ART = """
<div class="machine-scene">
 <div class="washer"><div class="washer-panel"><i></i><b></b></div><div class="washer-door"><div></div></div></div>
 <div class="washer washer-main"><div class="washer-panel"><i></i><b></b></div><div class="washer-door"><div></div></div></div>
 <div class="washer"><div class="washer-panel"><i></i><b></b></div><div class="washer-door"><div></div></div></div>
 <div class="scene-bubble bubble-one"></div><div class="scene-bubble bubble-two"></div>
</div>
"""

CSS = """
:root { color-scheme:light; }
html,body,#root,gradio-app,.gradio-container { background:#f5f7fa !important;color:#1b2b43 !important;color-scheme:light !important; }
body { margin:0 !important; }
.gradio-container { width:100% !important;max-width:none !important;padding:0 clamp(12px,4vw,64px) 40px !important;box-sizing:border-box !important; }
main { width:100% !important;max-width:1440px !important;margin:auto !important; }
footer { display:none !important; }
#brandbar { display:flex;align-items:center;justify-content:space-between;background:#fff;padding:17px 26px;border-bottom:1px solid #e7ebf1; }
#brand-lock { display:flex;align-items:center;gap:11px; }
#brand-mark { width:42px;height:42px;display:grid;place-items:center;border-radius:13px;background:#eaf4ff;color:#138bc3;font-size:21px; }
#brand-name { font-size:18px;font-weight:850;letter-spacing:-.3px;color:#142849; }
#brand-caption { font-size:11px;color:#8390a0;margin-top:2px; }
#brand-hours { color:#5c6d82;font-size:12px;font-weight:650; }
button[role="tab"] { padding:13px 22px !important;border-radius:0 !important;border-bottom:2px solid transparent !important;color:#65758a !important;font-weight:700 !important; }
button[role="tab"][aria-selected="true"] { color:#147eb8 !important;border-bottom:2px solid #178ec8 !important;background:transparent !important; }
[data-testid="tabitem"] { padding-top:0 !important; }
#public-nav { display:flex;align-items:center;justify-content:space-between;background:white;padding:13px 4px;border-bottom:1px solid #e6ebf0; }
#public-nav a { color:#55667b;text-decoration:none;font-size:11px;font-weight:750; }
#public-nav .nav-logo { font-size:18px;color:#132849;letter-spacing:1px;font-weight:900; }
#public-nav .nav-links { display:flex;align-items:center;gap:26px; }
.nav-cta { color:white !important;background:#168bc7;padding:10px 17px;border-radius:999px; }
#hero { display:grid;grid-template-columns:1fr 1.05fr;align-items:center;gap:24px;padding:46px clamp(22px,6vw,80px);min-height:360px;overflow:hidden;border-radius:0 0 22px 22px;background:radial-gradient(ellipse at 78% 25%,#385f8e,#1b355a 48%,#111f38 100%); }
.hero-copy { position:relative;z-index:1;max-width:510px; }
.hero-kicker { color:#9be4e8;font-size:11px;font-weight:850;letter-spacing:1.4px;text-transform:uppercase; }
.hero-title { color:white;font-weight:850;font-size:clamp(38px,5vw,64px);line-height:1.03;letter-spacing:-2.5px;margin:17px 0 14px; }
.hero-title span { color:#77d9e4; }
.hero-description { color:#d5dfec;font-size:14px;line-height:1.75;max-width:430px; }
.hero-actions { display:flex;align-items:center;gap:18px;margin-top:24px; }
.hero-button { display:inline-block;padding:12px 19px;background:#168bc7;border-radius:999px;color:white!important;text-decoration:none;font-size:12px;font-weight:800; }
.hero-secondary { color:#e7edf6!important;text-decoration:none;font-size:12px;font-weight:700; }
.machine-scene { position:relative;display:flex;align-items:end;justify-content:center;gap:14px;min-height:270px;padding:20px 15px 0; }
.washer { width:26%;height:210px;border-radius:15px 15px 8px 8px;background:linear-gradient(145deg,#fff,#cfdae7);box-shadow:0 22px 35px #07162a66;padding:12px 10px;position:relative;z-index:1; }
.washer-main { height:247px;width:30%;padding:13px; }
.washer-panel { height:26px;background:#edf2f7;border-radius:6px;display:flex;align-items:center;gap:8px;padding:0 8px; }
.washer-panel i { width:7px;height:7px;background:#1aa6c4;border-radius:50%; }
.washer-panel b { width:34px;height:6px;border-radius:5px;background:#c5d1df; }
.washer-door { margin:20px auto 0;width:82%;aspect-ratio:1;border-radius:50%;background:#213854;padding:7px;box-shadow:inset 0 0 0 5px #aebed0; }
.washer-door div { height:100%;border-radius:50%;background:radial-gradient(circle at 35% 33%,#c4f2f3,#52bad0 44%,#174a78 76%); }
.scene-bubble { position:absolute;border-radius:50%;background:#74e0e1;opacity:.22; }
.bubble-one { width:70px;height:70px;right:4%;top:3%; }
.bubble-two { width:30px;height:30px;left:6%;top:10%; }
#feature-strip { position:relative;z-index:2;display:grid;grid-template-columns:repeat(4,1fr);gap:11px;width:min(100% - 44px,1080px);margin:-25px auto 0; }
.feature-card { display:flex;align-items:center;gap:11px;padding:15px;background:white;border:1px solid #e4ebf0;border-radius:14px;box-shadow:0 11px 26px #192f4a18; }
.feature-icon { width:35px;height:35px;display:grid;place-items:center;border-radius:11px;background:#e9f7fa;color:#168bb7;font-size:17px;flex:none; }
.feature-card strong { display:block;color:#203650;font-size:11px; }
.feature-card small { color:#8290a0;font-size:10px;display:block;margin-top:3px; }
.section { padding:62px clamp(12px,4vw,48px);scroll-margin-top:15px; }
.section-heading { text-align:center;max-width:620px;margin:0 auto 27px; }
.section-eyebrow { color:#1787bd;font-size:10px;font-weight:850;letter-spacing:1.5px; }
.section-heading h2 { color:#1a2c46;font-size:29px;letter-spacing:-.8px;margin:9px 0 7px; }
.section-heading p { color:#7b8999;font-size:12px;line-height:1.65;margin:0; }
.service-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;max-width:1050px;margin:auto; }
.service-card { background:#fff;border:1px solid #e4eaf0;border-radius:17px;padding:21px;box-shadow:0 8px 23px #2239580b; }
.service-icon { width:38px;height:38px;border-radius:12px;background:#eaf6fb;color:#1588b9;display:grid;place-items:center;font-size:20px; }
.service-card h3 { color:#203650;font-size:15px;margin:15px 0 6px; }
.service-card p { color:#7b8999;font-size:11px;line-height:1.6;min-height:35px; }
.service-card strong { display:block;color:#167fb5;font-size:23px;margin-top:14px; }
.service-card small { color:#7f8d9d;font-size:11px;font-weight:600; }
.service-time { border-top:1px solid #edf0f4;margin-top:12px;padding-top:11px;color:#60758a;font-size:11px; }
.soft { background:#edf3f7; }
.steps { display:grid;grid-template-columns:repeat(3,1fr);gap:15px;max-width:950px;margin:auto; }
.step-card { background:white;padding:22px;border:1px solid #e5ebf0;border-radius:16px; }
.step-card b { color:#178bc3;font-size:11px;letter-spacing:1px; }
.step-card h3 { color:#213650;font-size:14px;margin:11px 0 6px; }
.step-card p { color:#7b8999;font-size:11px;line-height:1.6;margin:0; }
.form-panel,#buyer-chat { max-width:850px;margin:auto;background:white;border:1px solid #e2e9ef;border-radius:18px;padding:22px;box-shadow:0 10px 28px #1936550b; }
.form-panel h3 { color:#203650;margin:0 0 5px;font-size:17px; }
.form-panel p { color:#8390a0;margin:0 0 16px;font-size:11px; }
#buyer-submit,#admin-submit,#admin-update,#admin-refresh { min-height:43px;border-radius:11px !important;font-weight:750 !important; }
button.primary { background:#168bc7 !important;color:#fff !important;border-color:#168bc7 !important; }
button.primary:hover { background:#0e71a6 !important; }
#track-result { padding:14px;background:#eff8fc;border:1px solid #d8ebf3;border-radius:13px; }
#buyer-chat { padding:18px; }
#admin-login { max-width:440px;margin:55px auto;background:#fff;border:1px solid #e2e9ef;border-radius:18px;padding:25px;box-shadow:0 12px 30px #19365512; }
#admin-workspace { max-width:1200px;margin:20px auto;background:#f5f7fa; }
.admin-heading h2 { color:#1c304b;font-size:26px;margin:7px 0; }
.admin-heading p { color:#77879a;font-size:12px; }
#metric-total,#metric-active,#metric-ready,#metric-revenue { background:white !important;border:1px solid #e1e8ef !important;border-radius:15px !important;padding:13px !important;box-shadow:0 5px 16px #1936550b !important; }
#metric-total label,#metric-active label,#metric-ready label,#metric-revenue label { color:#77879a !important;font-size:11px !important; }
#metric-total input,#metric-active input,#metric-ready input,#metric-revenue input { color:#167fb5 !important;background:white !important;border:0 !important;font-size:24px !important;font-weight:850 !important; }
#recent-orders { overflow:hidden;background:white !important;border:1px solid #e1e8ef !important;border-radius:14px !important; }
thead,th { background:#edf4f8 !important;color:#34516d !important;font-weight:750 !important; }
td,th { border-color:#e5ecf1 !important;padding:10px 12px !important; }
input,textarea,select { background:white !important;color:#203650 !important;border-color:#dce6ee !important;border-radius:10px !important; }
#site-footer { padding:22px;text-align:center;color:#8793a1;font-size:11px;border-top:1px solid #e5eaf0; }
@media(max-width:820px) {
 #hero { grid-template-columns:1fr;padding:38px 22px 25px; }
 .machine-scene { min-height:210px; }
 .washer { height:165px; }
 .washer-main { height:195px; }
 #feature-strip { grid-template-columns:repeat(2,1fr);width:calc(100% - 20px);margin-top:-18px;gap:8px; }
 .feature-card { padding:11px 9px; }
 .service-grid,.steps { grid-template-columns:1fr;max-width:560px; }
 #public-nav .nav-links { gap:12px; }
 #public-nav a { font-size:9px; }
}
@media(max-width:520px) {
 .gradio-container { padding:0 9px 24px !important; }
 #brandbar { padding:12px 9px; }
 #brand-name { font-size:15px; }
 #brand-caption,#brand-hours { display:none; }
 #public-nav { flex-wrap:wrap;gap:10px; }
 #public-nav .nav-links { width:100%;justify-content:space-between;gap:4px; }
 #public-nav .nav-logo { width:100%; }
 .nav-cta { padding:8px 10px; }
 .hero-title { font-size:39px; }
 .section { padding:45px 10px; }
 .section-heading h2 { font-size:24px; }
 .form-panel,#buyer-chat { padding:15px; }
}
"""

with gr.Blocks(title="Laundry Halilintar") as demo:
    gr.HTML("<div id='brandbar'><div id='brand-lock'><div id='brand-mark'>✦</div><div><div id='brand-name'>LAUNDRY HALILINTAR</div><div id='brand-caption'>Perawatan pakaian yang lebih mudah</div></div></div><div id='brand-hours'>Senin—Minggu &nbsp;·&nbsp; 07.00—20.00</div></div>")
    with gr.Tabs():
        with gr.Tab("Untuk Pembeli"):
            gr.HTML("<nav id='public-nav'><a class='nav-logo' href='#top'>HALILINTAR</a><div class='nav-links'><a href='#buyer-services'>LAYANAN</a><a href='#buyer-process'>CARA KERJA</a><a href='#buyer-track'>CEK PESANAN</a><a class='nav-cta' href='#buyer-order'>PESAN SEKARANG</a></div></nav>")
            gr.HTML("<section id='top'><div id='hero'><div class='hero-copy'><div class='hero-kicker'>LAUNDRY CARE, MADE SIMPLE</div><h1 class='hero-title'>Pakaian bersih,<br><span>hari lebih ringan.</span></h1><p class='hero-description'>Titipkan cucianmu kepada Laundry Halilintar. Kami bantu pakaian kembali bersih, rapi, dan siap menemani aktivitasmu.</p><div class='hero-actions'><a class='hero-button' href='#buyer-order'>Pesan laundry &nbsp;→</a><a class='hero-secondary' href='#buyer-services'>Lihat layanan</a></div></div>" + MACHINE_ART + "</div></section><div id='feature-strip'><div class='feature-card'><div class='feature-icon'>✧</div><div><strong>Penanganan teliti</strong><small>Pakaian dijaga dengan rapi</small></div></div><div class='feature-card'><div class='feature-icon'>◷</div><div><strong>Estimasi jelas</strong><small>Pantau status pesanan</small></div></div><div class='feature-card'><div class='feature-icon'>◇</div><div><strong>Pilihan praktis</strong><small>Layanan sesuai kebutuhan</small></div></div><div class='feature-card'><div class='feature-icon'>♡</div><div><strong>Mulai Rp7.000/kg</strong><small>Harga layanan reguler</small></div></div></div>")
            gr.HTML("<section id='buyer-services' class='section'><div class='section-heading'><div class='section-eyebrow'>LAYANAN KAMI</div><h2>Perawatan pas untuk pakaianmu</h2><p>Pilih layanan sesuai kebutuhan. Harga dan estimasi ditampilkan sebelum pesanan dikirim.</p></div>" + service_cards_markup() + "</section>")
            gr.HTML("<section id='buyer-process' class='section soft'><div class='section-heading'><div class='section-eyebrow'>MUDAH DAN PRAKTIS</div><h2>Proses dibuat sederhana</h2><p>Cukup beberapa langkah untuk menitipkan dan mengambil laundry.</p></div><div class='steps'><article class='step-card'><b>01 / PESAN</b><h3>Pilih layanan</h3><p>Isi data kontak, pilih layanan, dan masukkan berat cucianmu.</p></article><article class='step-card'><b>02 / PROSES</b><h3>Kami kerjakan</h3><p>Simpan kode pesanan. Admin memperbarui status saat cucian diproses.</p></article><article class='step-card'><b>03 / AMBIL</b><h3>Cucian siap</h3><p>Cek status dengan kode pesanan dan nomor WhatsApp terdaftar.</p></article></div></section>")
            gr.HTML("<section id='buyer-order' class='section'><div class='section-heading'><div class='section-eyebrow'>MULAI DARI SINI</div><h2>Pesan layanan laundry</h2><p>Kode pesanan muncul setelah pesanan berhasil dikirim.</p></div></section>")
            with gr.Column(elem_id="buyer-order-form", elem_classes=["form-panel"]):
                gr.Markdown("### Formulir pesanan\nJam buka setiap hari, 07.00–20.00.")
                if not ADMIN_DB:
                    gr.Markdown("Info: pemesanan online demo aktif setelah koneksi admin Supabase disiapkan di file .env lokal.")
                with gr.Row():
                    with gr.Column():
                        buyer_name = gr.Textbox(label="Nama lengkap", placeholder="Nama kamu")
                        buyer_phone = gr.Textbox(label="Nomor WhatsApp", placeholder="08xxxxxxxxxx")
                        buyer_service = gr.Dropdown(choices=service_choices(), label="Pilih layanan")
                    with gr.Column():
                        buyer_weight = gr.Number(label="Perkiraan berat (kg)", minimum=0.1, value=2, precision=2)
                        buyer_payment = gr.Dropdown(["Tunai", "QRIS", "Transfer Bank"], value="Tunai", label="Rencana pembayaran")
                        buyer_notes = gr.Textbox(label="Catatan khusus (opsional)", lines=2, placeholder="Contoh: pakaian putih dipisah")
                buyer_submit = gr.Button("Kirim pesanan", variant="primary", elem_id="buyer-submit")
                buyer_result = gr.Markdown()
            gr.HTML("<section id='buyer-track' class='section soft'><div class='section-heading'><div class='section-eyebrow'>PELACAKAN</div><h2>Cek status cucianmu</h2><p>Gunakan kode pesanan dan nomor WhatsApp yang dipakai saat memesan.</p></div></section>")
            with gr.Column(elem_classes=["form-panel"]):
                with gr.Row():
                    track_code = gr.Textbox(label="Kode pesanan", placeholder="LH-YYMMDD-XXXXXXXX")
                    track_phone = gr.Textbox(label="Nomor WhatsApp")
                track_button = gr.Button("Cek status", variant="primary")
                track_result = gr.Markdown(elem_id="track-result")
            gr.HTML("<section class='section'><div class='section-heading'><div class='section-eyebrow'>ASISTEN VIRTUAL</div><h2>Ada yang ingin ditanyakan?</h2><p>Asisten AI membantu informasi layanan dan perawatan pakaian.</p></div></section>")
            with gr.Column(elem_id="buyer-chat", elem_classes=["form-panel"]):
                buyer_chat = gr.Chatbot(value=initial_chat(), height=300, show_label=False)
                with gr.Row():
                    buyer_chat_input = gr.Textbox(placeholder="Tanyakan layanan, harga, atau jam buka...", show_label=False, scale=8)
                    buyer_chat_send = gr.Button("Kirim", variant="primary", scale=1)
            gr.HTML("<div id='site-footer'>© 2026 Laundry Halilintar · Buka setiap hari, 07.00–20.00</div>")

        with gr.Tab("Admin"):
            admin_session = gr.State(False)
            with gr.Column(elem_id="admin-login", visible=True) as admin_login_panel:
                gr.Markdown("## Portal admin\nKelola pesanan Laundry Halilintar.")
                if not ADMIN_DB:
                    gr.Markdown("**Koneksi database belum diatur.** Isi SUPABASE_SERVICE_ROLE_KEY di .env lokal.")
                if not ADMIN_PIN:
                    gr.Markdown("Atur ADMIN_PIN pada .env lokal untuk membuat PIN admin.")
                admin_pin_input = gr.Textbox(label="PIN admin", type="password", placeholder="Masukkan PIN")
                admin_login_button = gr.Button("Masuk sebagai admin", variant="primary")
                admin_login_message = gr.Markdown()
            with gr.Column(visible=False, elem_id="admin-workspace") as admin_workspace:
                gr.HTML("<div class='section-heading admin-heading'><div class='section-eyebrow'>PANEL PENGELOLAAN</div><h2>Ringkasan operasional</h2><p>Kelola transaksi, status cucian, dan pembayaran.</p></div>")
                admin_logout_button = gr.Button("Keluar dari admin", size="sm")
                with gr.Row(equal_height=True):
                    total_card = gr.Number(label="Total pesanan", value=0, interactive=False, elem_id="metric-total")
                    active_card = gr.Number(label="Sedang berjalan", value=0, interactive=False, elem_id="metric-active")
                    ready_card = gr.Number(label="Siap diambil", value=0, interactive=False, elem_id="metric-ready")
                    revenue_card = gr.Textbox(label="Pembayaran lunas", value="Rp0", interactive=False, elem_id="metric-revenue")
                admin_refresh = gr.Button("Muat ulang ringkasan", elem_id="admin-refresh")
                gr.Markdown("### Pesanan terbaru")
                orders_table = gr.Dataframe(headers=["Kode", "Pelanggan", "Layanan", "Status", "Pembayaran", "Total"], interactive=False, wrap=True, elem_id="recent-orders")
                gr.Markdown("### Catat pesanan di kasir")
                with gr.Row():
                    with gr.Column():
                        customer_name = gr.Textbox(label="Nama pelanggan")
                        customer_phone = gr.Textbox(label="Nomor WhatsApp")
                        service_select = gr.Dropdown(choices=service_choices(), label="Layanan")
                    with gr.Column():
                        weight_input = gr.Number(label="Berat (kg)", minimum=0.1, value=1, precision=2)
                        payment_select = gr.Dropdown(["Belum dibayar", "Tunai", "QRIS", "Transfer Bank"], value="Belum dibayar", label="Metode pembayaran")
                        paid_select = gr.Radio(["Belum Lunas", "Lunas"], value="Belum Lunas", label="Status pembayaran")
                notes_input = gr.Textbox(label="Catatan cucian", lines=2)
                create_button = gr.Button("Simpan pesanan", variant="primary", elem_id="admin-submit")
                order_notice = gr.Markdown()
                gr.Markdown("### Perbarui status pesanan")
                with gr.Row():
                    update_code = gr.Textbox(label="Kode pesanan")
                    update_status_select = gr.Dropdown(["Diterima", "Diproses", "Siap Diambil", "Selesai", "Dibatalkan"], value="Diproses", label="Status pesanan")
                with gr.Row():
                    update_paid_select = gr.Dropdown(["Belum Lunas", "Lunas"], value="Belum Lunas", label="Status pembayaran")
                    update_payment_select = gr.Dropdown(["Belum dibayar", "Tunai", "QRIS", "Transfer Bank"], value="Belum dibayar", label="Metode pembayaran")
                update_button = gr.Button("Perbarui pesanan", variant="primary", elem_id="admin-update")
                update_notice = gr.Markdown()
                gr.Markdown("### Katalog layanan")
                gr.Dataframe(headers=["Layanan", "Deskripsi", "Harga/kg", "Estimasi (jam)"], interactive=False, value=[
                    [row.get("name"), row.get("description"), format_rupiah(row.get("price_per_kg")), row.get("estimated_hours")]
                    for row in get_service_rows()
                ])

    admin_outputs = [admin_login_message, admin_session, admin_login_panel, admin_workspace, total_card, active_card, ready_card, revenue_card, orders_table]
    admin_login_button.click(login_admin, inputs=[admin_pin_input], outputs=admin_outputs)
    admin_logout_button.click(logout_admin, outputs=admin_outputs)
    admin_refresh.click(refresh_dashboard_for_admin, inputs=[admin_session], outputs=[total_card, active_card, ready_card, revenue_card, orders_table])
    create_button.click(create_order, [customer_name, customer_phone, service_select, weight_input, payment_select, paid_select, notes_input, admin_session], [order_notice, total_card, active_card, ready_card, revenue_card, orders_table, service_select])
    update_button.click(update_order, [update_code, update_status_select, update_paid_select, update_payment_select, admin_session], [update_notice, total_card, active_card, ready_card, revenue_card, orders_table])
    buyer_submit.click(create_buyer_order, [buyer_name, buyer_phone, buyer_service, buyer_weight, buyer_payment, buyer_notes], outputs=buyer_result)
    track_button.click(track_buyer_order, [track_code, track_phone], outputs=track_result)
    buyer_chat_input.submit(ask_chat, [buyer_chat_input, buyer_chat], [buyer_chat, buyer_chat_input])
    buyer_chat_send.click(ask_chat, [buyer_chat_input, buyer_chat], [buyer_chat, buyer_chat_input])

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(primary_hue="sky", secondary_hue="blue", neutral_hue="slate"), css=CSS)



