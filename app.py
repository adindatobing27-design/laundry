import base64
import html
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).parent
QRIS_IMAGE_PATH = ROOT / "assets" / "qris-laundry.jpg"
QRIS_DATA_URI = (
    "data:image/jpeg;base64," + base64.b64encode(QRIS_IMAGE_PATH.read_bytes()).decode("ascii")
    if QRIS_IMAGE_PATH.exists()
    else ""
)
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
ADMIN_SUPABASE_KEY = SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()

if ADMIN_SUPABASE_KEY.startswith("sb_publishable_"):
    ADMIN_DB_CONFIG_ERROR = (
        "Key di SUPABASE_SERVICE_ROLE_KEY adalah publishable key. Isi SUPABASE_SECRET_KEY "
        "dengan Secret key (awalan sb_secret_) dari Supabase Dashboard → Project Settings → API Keys."
    )
    ADMIN_SUPABASE_KEY = ""
elif not ADMIN_SUPABASE_KEY:
    ADMIN_DB_CONFIG_ERROR = "Secret key Supabase belum diisi pada SUPABASE_SECRET_KEY di file .env lokal."
else:
    ADMIN_DB_CONFIG_ERROR = ""


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
ADMIN_DB = make_client(ADMIN_SUPABASE_KEY)


def load_services():
    if PUBLIC_DB:
        try:
            return PUBLIC_DB.table("services").select(
                "name, description, price_per_kg, estimated_hours, unit_type"
            ).eq("is_active", True).execute().data or []
        except Exception as error:
            print(f"Layanan Supabase belum dapat dibaca ({type(error).__name__}).")
    if ADMIN_DB:
        try:
            return ADMIN_DB.table("services").select(
                "name, description, price_per_kg, estimated_hours, unit_type"
            ).eq("is_active", True).execute().data or []
        except Exception as error:
            print(f"Katalog layanan admin belum dapat dibaca ({type(error).__name__}).")
    return []


print("Memuat katalog layanan...")
SERVICES = load_services()
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


def payment_guidance_markup(method):
    if method == "QRIS":
        image = (
            f"<img class='payment-qris-image' src='{QRIS_DATA_URI}' alt='Kode QRIS Laundry Halilintar'>"
            if QRIS_DATA_URI else "<div class='payment-qris-missing'>File QRIS belum ditemukan di folder assets.</div>"
        )
        return (
            "<section class='payment-guide-card payment-guide-qris'>"
            "<div class='payment-guide-copy'><span class='payment-guide-eyebrow'>PEMBAYARAN QRIS</span>"
            "<h3>Scan untuk membayar</h3><p>Scan QRIS ini dari aplikasi pembayaran. Setelah pesanan dibuat, masukkan nominal total yang tertera pada konfirmasi.</p>"
            "<small>Pembayaran akan tercatat lunas setelah diverifikasi oleh admin.</small></div>"
            f"<div class='payment-qris-frame'>{image}</div></section>"
        )
    if method == "Transfer Bank":
        return (
            "<section class='payment-guide-card payment-guide-bank'>"
            "<div class='payment-guide-copy'><span class='payment-guide-eyebrow'>TRANSFER BANK</span>"
            "<h3>Rekening BNI</h3><p>Transfer sesuai total pesanan yang tampil setelah pesanan dibuat.</p></div>"
            "<div class='bank-account-card'><span>Bank BNI</span><strong>9800000000</strong><small>a.n. Adinda Tobing</small></div>"
            "<small class='payment-guide-footnote'>Pembayaran akan tercatat lunas setelah diverifikasi oleh admin.</small></section>"
        )
    return (
        "<section class='payment-guide-card payment-guide-cash'>"
        "<span class='payment-guide-eyebrow'>PEMBAYARAN TUNAI</span>"
        "<h3>Bayar saat mengambil cucian</h3>"
        "<p>Siapkan pembayaran sesuai total pesanan ketika cucian sudah siap diambil.</p></section>"
    )


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


METRIC_ICONS = {
    "cart": "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M3 4h2l2.2 11.1a2 2 0 0 0 2 1.6h8.7a2 2 0 0 0 1.9-1.4L22 9H7'/><circle cx='10' cy='20' r='1.4'/><circle cx='18' cy='20' r='1.4'/></svg>",
    "calendar": "<svg viewBox='0 0 24 24' aria-hidden='true'><rect x='3' y='5' width='18' height='16' rx='2'/><path d='M16 3v4M8 3v4M3 10h18M8 14h2m4 0h2m-8 3h2m4 0h2'/></svg>",
    "check": "<svg viewBox='0 0 24 24' aria-hidden='true'><circle cx='12' cy='12' r='10'/><path d='m7 12 3.2 3.2L17.5 8'/></svg>",
    "shirt": "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='m7 4 5 3 5-3 4 3-2 4-3-1v10H8V10l-3 1-2-4 4-3Z'/></svg>",
}


def render_metric_card(title, value, icon, tone):
    return (
        f"<article class='metric-tile metric-{tone}'>"
        f"<div class='metric-tile-icon'>{METRIC_ICONS[icon]}</div>"
        f"<div class='metric-tile-content'><div class='metric-tile-title'>{html.escape(str(title))}</div>"
        f"<div class='metric-tile-value'>{html.escape(str(value))}</div></div></article>"
    )


def render_orders_table(rows):
    columns = ["Kode", "Pelanggan", "Layanan", "Status", "Pembayaran", "Total"]
    head = "".join(f"<th>{html.escape(label)}</th>" for label in columns)
    body = []
    for row in rows:
        code, customer, service, status, payment, total = (list(row) + [""] * 6)[:6]
        status_class = "ready" if status == "Siap Diambil" else "done" if status == "Selesai" else "cancelled" if status == "Dibatalkan" else "progress"
        payment_class = "paid" if payment == "Lunas" else "unpaid"
        body.append(
            "<tr>"
            f"<td class='order-code-cell'>{html.escape(str(code or '—'))}</td>"
            f"<td>{html.escape(str(customer or '—'))}</td>"
            f"<td>{html.escape(str(service or '—'))}</td>"
            f"<td><span class='table-pill {status_class}'>{html.escape(str(status or '—'))}</span></td>"
            f"<td><span class='table-pill {payment_class}'>{html.escape(str(payment or '—'))}</span></td>"
            f"<td class='order-total-cell'>{html.escape(str(total or '—'))}</td></tr>"
        )
    return f"<div class='custom-table-scroll'><table class='custom-dashboard-table'><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def render_service_table():
    body = []
    for row in get_service_rows():
        body.append(
            "<tr>"
            f"<td><span class='service-name-cell'>{html.escape(str(row.get('name') or '—'))}</span></td>"
            f"<td>{html.escape(str(row.get('description') or '—'))}</td>"
            f"<td class='order-total-cell'>{html.escape(format_rupiah(row.get('price_per_kg')))}</td>"
            f"<td>{html.escape(str(row.get('estimated_hours') or '—'))}</td></tr>"
        )
    return "<div class='custom-table-scroll'><table class='custom-dashboard-table service-table'><thead><tr><th>Layanan</th><th>Deskripsi</th><th>Harga/kg</th><th>Estimasi (jam)</th></tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"


def dashboard_outputs(snapshot):
    total, active, ready, revenue, rows = snapshot
    return (
        render_metric_card("Total pesanan", total, "cart", "blue"),
        render_metric_card("Sedang berjalan", active, "calendar", "sky"),
        render_metric_card("Siap diambil", ready, "check", "mint"),
        render_metric_card("Pembayaran lunas", revenue, "shirt", "lilac"),
        render_orders_table(rows),
    )


def create_order_record(name, phone, service_label, weight, payment_method, paid, notes="", buyer=None):
    if not ADMIN_DB:
        return None, None, ADMIN_DB_CONFIG_ERROR or "Sambungan admin Supabase belum disiapkan."
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
        if buyer:
            customer_result = ADMIN_DB.table("customers").select("id").eq("auth_user_id", buyer["id"]).limit(1).execute().data
        else:
            customer_result = ADMIN_DB.table("customers").select("id").eq("phone", phone).limit(1).execute().data
        if customer_result:
            customer_id = customer_result[0]["id"]
            customer_values = {"name": name}
            if buyer:
                customer_values.update({"phone": phone, "email": buyer.get("email"), "auth_user_id": buyer["id"]})
            ADMIN_DB.table("customers").update(customer_values).eq("id", customer_id).execute()
        else:
            customer_values = {"name": name, "phone": phone}
            if buyer:
                customer_values.update({"email": buyer.get("email"), "auth_user_id": buyer["id"]})
            customer_id = ADMIN_DB.table("customers").insert(customer_values).execute().data[0]["id"]
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
        code = getattr(error, "code", None)
        message = getattr(error, "message", None) or str(error)
        detail = f" [{code}]" if code else ""
        message = " ".join(str(message).split())[:240]
        return None, None, f"Pesanan belum tersimpan{detail}: {message}"


def create_order(name, phone, service_label, weight, payment_method, paid, notes, is_admin):
    if not is_admin:
        snap = (0, 0, 0, format_rupiah(0), [])
        return "Silakan login admin terlebih dahulu.", *dashboard_outputs(snap), gr.update(choices=service_choices())
    code, total, error = create_order_record(name, phone, service_label, weight, payment_method, paid, notes)
    snap = get_dashboard()
    if error:
        return error, *dashboard_outputs(snap), gr.update(choices=service_choices())
    return f"Pesanan {code} berhasil dicatat. Total {format_rupiah(total)}.", *dashboard_outputs(snap), gr.update(choices=service_choices(), value=None)


def complete_buyer_login(access_token):
    if not access_token:
        return None, "Kamu belum login. Masuk dengan akun pembeli untuk membuat pesanan."
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None, "Konfigurasi Supabase publik belum lengkap di file .env."
    try:
        from supabase import create_client

        auth_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        response = auth_client.auth.get_user(access_token)
        user = response.user
        email = (getattr(user, "email", "") or "").strip()
        metadata = getattr(user, "user_metadata", {}) or {}
        name = str(metadata.get("full_name") or metadata.get("name") or (email.split("@")[0] if email else "Pembeli"))
        return {"id": str(user.id), "email": email, "name": str(name), "access_token": access_token}, f"Login sebagai **{html.escape(name)}** ({html.escape(email)})."
    except Exception:
        return None, "Sesi akun belum berhasil divalidasi. Coba masuk kembali."


def register_buyer(email, password):
    email = (email or "").strip().lower()
    password = password or ""
    if not email or "@" not in email:
        return None, "Masukkan alamat email yang valid."
    if ADMIN_EMAIL and secrets.compare_digest(email, ADMIN_EMAIL):
        return None, "Email admin khusus untuk tab Admin. Gunakan email lain untuk akun pembeli."
    if len(password) < 8:
        return None, "Password minimal 8 karakter."
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None, "Konfigurasi Supabase belum lengkap di file .env."
    try:
        from supabase import create_client

        auth_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        response = auth_client.auth.sign_up({"email": email, "password": password})
        session = getattr(response, "session", None)
        if not session or not getattr(session, "access_token", None):
            return None, "Akun berhasil didaftarkan. Cek email untuk konfirmasi, lalu masuk di sini."
        buyer_session, message = complete_buyer_login(session.access_token)
        return buyer_session, message
    except Exception:
        return None, "Pendaftaran gagal. Email mungkin sudah terdaftar, atau pengaturan Auth Supabase perlu diperiksa."


def login_buyer(email, password):
    email = (email or "").strip().lower()
    if not email or not password:
        return None, "Masukkan email dan password pembeli."
    if ADMIN_EMAIL and secrets.compare_digest(email, ADMIN_EMAIL):
        return None, "Email tersebut khusus untuk tab Admin."
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None, "Konfigurasi Supabase belum lengkap di file .env."
    try:
        from supabase import create_client

        auth_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        response = auth_client.auth.sign_in_with_password({"email": email, "password": password})
        session = getattr(response, "session", None)
        if not session or not getattr(session, "access_token", None):
            return None, "Login gagal. Periksa email dan password pembeli."
        return complete_buyer_login(session.access_token)
    except Exception:
        return None, "Login gagal. Periksa email/password atau konfirmasi email melalui inbox."


def logout_buyer():
    return None, "Kamu sudah keluar dari akun pembeli."


def create_buyer_order(name, phone, service_label, weight, payment_method, notes, buyer_session):
    if not buyer_session:
        return "Silakan masuk ke akun pembeli terlebih dahulu sebelum membuat pesanan."
    validated_session, session_message = complete_buyer_login(buyer_session.get("access_token"))
    if not validated_session or validated_session.get("id") != buyer_session.get("id"):
        return "Sesi login berakhir. Silakan masuk kembali."
    buyer = {"id": validated_session["id"], "email": validated_session["email"]}
    name = (name or "").strip() or validated_session["name"]
    code, total, error = create_order_record(name, phone, service_label, weight, payment_method, "Belum Lunas", notes, buyer=buyer)
    if error:
        return error
    return f"Pesanan berhasil dikirim! Simpan kode **{code}** untuk mengecek status. Perkiraan total {format_rupiah(total)}. Pembayaran dapat diselesaikan saat proses pesanan."


def track_buyer_order(order_code, phone):
    if not ADMIN_DB:
        return f"Pelacakan belum siap. {ADMIN_DB_CONFIG_ERROR or 'Koneksi admin Supabase perlu diatur terlebih dahulu.'}"
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


def verify_admin_credentials(email, password):
    if not ADMIN_DB:
        return False, ADMIN_DB_CONFIG_ERROR or "Koneksi admin Supabase belum siap. Isi SUPABASE_SECRET_KEY di .env lokal."
    if not ADMIN_EMAIL:
        return False, "Email admin belum diatur pada ADMIN_EMAIL di file .env lokal."
    email = (email or "").strip().lower()
    if not email or not password:
        return False, "Masukkan email dan password akun admin Supabase."
    if not secrets.compare_digest(email, ADMIN_EMAIL):
        return False, "Akun ini tidak terdaftar sebagai admin."
    try:
        from supabase import create_client

        auth_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        response = auth_client.auth.sign_in_with_password({"email": email, "password": password})
        authenticated_email = (getattr(response.user, "email", "") or "").strip().lower()
        if not authenticated_email or not secrets.compare_digest(authenticated_email, ADMIN_EMAIL):
            return False, "Login ditolak: akun Supabase ini bukan email admin yang diizinkan."
    except Exception:
        return False, "Login gagal. Periksa email/password akun Supabase dan pastikan emailnya sudah dikonfirmasi."
    return True, "Login admin berhasil."


def portal_response(message, role=None, buyer=None):
    is_admin = role == "admin"
    is_buyer = role == "buyer"
    stats = dashboard_outputs(get_dashboard() if is_admin else (0, 0, 0, format_rupiah(0), []))
    greeting = f"### Halo, {html.escape(buyer['name'])}" if is_buyer and buyer else ""
    return (
        message,
        is_admin,
        buyer if is_buyer else None,
        gr.update(visible=not (is_admin or is_buyer)),
        gr.update(visible=is_buyer),
        gr.update(visible=is_admin),
        *stats,
        greeting,
    )


def login_from_portal(email, password):
    email = (email or "").strip().lower()
    if ADMIN_EMAIL and secrets.compare_digest(email, ADMIN_EMAIL):
        success, message = verify_admin_credentials(email, password)
        return portal_response(message, role="admin" if success else None)
    buyer, message = login_buyer(email, password)
    return portal_response(message, role="buyer" if buyer else None, buyer=buyer)


def register_from_portal(email, password):
    buyer, message = register_buyer(email, password)
    if buyer:
        message = "Akun pembeli berhasil dibuat dan kamu sudah masuk."
    return portal_response(message, role="buyer" if buyer else None, buyer=buyer)


def logout_from_portal():
    return portal_response("Kamu sudah keluar. Masuk kembali untuk melanjutkan.")


def refresh_dashboard_for_admin(is_admin):
    return dashboard_outputs(get_dashboard() if is_admin else (0, 0, 0, format_rupiah(0), []))


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

FORM_ICONS = {
    "person": "<svg viewBox='0 0 24 24' aria-hidden='true'><circle cx='12' cy='7.5' r='3.5'/><path d='M4.5 21v-2.3a7.5 7.5 0 0 1 15 0V21'/></svg>",
    "phone": "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M6.5 3.5 9 3l2 4-2 1.7a15 15 0 0 0 6.3 6.3L17 13l4 2-.5 2.5a3 3 0 0 1-3.3 2.4A17.5 17.5 0 0 1 4.1 6.8 3 3 0 0 1 6.5 3.5Z'/></svg>",
    "laundry": "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M4 8h16l-1.4 12H5.4L4 8Z'/><path d='M3 8h18M7 8l2-4m8 4-2-4M8 13c1.2-1.3 2.6-1.3 4 0s2.8 1.3 4 0'/></svg>",
    "scale": "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M12 3v17M5 6h14M8 6l-4 7h8L8 6Zm8 0-4 7h8l-4-7ZM7 21h10'/></svg>",
    "payment": "<svg viewBox='0 0 24 24' aria-hidden='true'><rect x='3' y='5' width='18' height='14' rx='2'/><path d='M3 9h18m-14 6h4'/></svg>",
    "status": "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M4 20v-6h4v6m4 0V9h4v11m4 0V4h4v16'/></svg>",
    "notes": "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v9a2.5 2.5 0 0 1-2.5 2.5H10l-5 4v-4.5a2.5 2.5 0 0 1-1-2v-9Z'/><path d='M8 8h8m-8 4h6'/></svg>",
    "data": "<svg viewBox='0 0 24 24' aria-hidden='true'><rect x='5' y='4' width='14' height='17' rx='2'/><path d='M9 4V2h6v2M8 9h8m-8 4h8m-8 4h6'/></svg>",
}


def order_field_header(icon, label):
    return f"<div class='order-field-title'>{FORM_ICONS[icon]}<span>{html.escape(label)}</span></div>"

CSS = """
:root { color-scheme:light; }
html,body,#root,gradio-app,.gradio-container { background:#f3f7fc !important;color:#142b4a !important;color-scheme:light !important; }
body { margin:0 !important; }
.gradio-container { width:100% !important;max-width:none !important;padding:0 clamp(12px,4vw,64px) 40px !important;box-sizing:border-box !important; }
main { width:100% !important;max-width:1440px !important;margin:auto !important; }
footer { display:none !important; }
#brandbar { display:flex;align-items:center;justify-content:space-between;background:#fff;padding:17px 26px;border-bottom:1px solid #e7ebf1; }
#brand-lock { display:flex;align-items:center;gap:11px; }
#brand-mark { width:42px;height:42px;display:grid;place-items:center;border-radius:13px;background:#eaf4ff;color:#138bc3;font-size:21px; }
#brand-name { font-size:18px;font-weight:850;letter-spacing:-.3px;color:#142849; }
#brand-caption { font-size:11px;color:#526780;margin-top:2px; }
#brand-hours { color:#314963;font-size:12px;font-weight:700; }
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
.section-heading p { color:#52647b;font-size:12px;line-height:1.65;margin:0; }
.service-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;max-width:1050px;margin:auto; }
.service-card { background:#fff;border:1px solid #e4eaf0;border-radius:17px;padding:21px;box-shadow:0 8px 23px #2239580b; }
.service-icon { width:38px;height:38px;border-radius:12px;background:#eaf6fb;color:#1588b9;display:grid;place-items:center;font-size:20px; }
.service-card h3 { color:#203650;font-size:15px;margin:15px 0 6px; }
.service-card p { color:#52647b;font-size:11px;line-height:1.6;min-height:35px; }
.service-card strong { display:block;color:#167fb5;font-size:23px;margin-top:14px; }
.service-card small { color:#7f8d9d;font-size:11px;font-weight:600; }
.service-time { border-top:1px solid #edf0f4;margin-top:12px;padding-top:11px;color:#60758a;font-size:11px; }
.soft { background:#edf3f7; }
.steps { display:grid;grid-template-columns:repeat(3,1fr);gap:15px;max-width:950px;margin:auto; }
.step-card { background:white;padding:22px;border:1px solid #e5ebf0;border-radius:16px; }
.step-card b { color:#178bc3;font-size:11px;letter-spacing:1px; }
.step-card h3 { color:#213650;font-size:14px;margin:11px 0 6px; }
.step-card p { color:#7b8999;font-size:11px;line-height:1.6;margin:0; }
.form-panel { max-width:850px;margin:auto;background:white;border:1px solid #e2e9ef;border-radius:18px;padding:22px;box-shadow:0 10px 28px #1936550b; }
.form-panel h3 { color:#203650;margin:0 0 5px;font-size:17px; }
.form-panel p { color:#52647b;margin:0 0 16px;font-size:11px; }
#buyer-submit,#admin-submit,#admin-update,#admin-refresh { min-height:43px;border-radius:11px !important;font-weight:750 !important; }
button.primary { background:#168bc7 !important;color:#fff !important;border-color:#168bc7 !important; }
button.primary:hover { background:#0e71a6 !important; }
#track-result { padding:16px 18px;background:#f1f8ff !important;color:#17365f !important;border:1px solid #c9dff4;border-radius:16px;box-shadow:0 6px 16px #1b4e8310; }
#track-result .prose,#track-result .prose p,#track-result .prose strong,#track-result .prose li { color:#17365f !important;opacity:1 !important; }
#track-result .prose { font-size:15px !important;line-height:1.75 !important; }
#track-result .prose p { margin:0 0 5px !important; }
#track-result .prose p:first-child { margin:0 0 10px !important;padding:0 0 9px !important;border-bottom:1px solid #d4e4f5;font-size:17px !important;font-weight:800 !important; }
#track-result .prose strong { color:#102b4d !important;font-weight:800 !important; }
#buyer-order-result { margin-top:12px;padding:13px 15px;border:1px solid #b9d8f2;border-radius:12px;background:#edf7ff !important;color:#17365f !important; }
#buyer-order-result .prose,#buyer-order-result .prose p { color:#17365f !important;opacity:1 !important;font-size:14px !important;line-height:1.65 !important; }
#buyer-order-result strong,#buyer-order-result .prose strong { display:inline-block;padding:2px 8px;border-radius:6px;background:#d7eaff !important;color:#102b4d !important;font-weight:850 !important; }
#admin-login { max-width:440px;margin:55px auto;background:#fff;border:1px solid #e2e9ef;border-radius:18px;padding:25px;box-shadow:0 12px 30px #19365512; }
#auth-screen { max-width:680px;margin:50px auto;background:#fff;border:1px solid #e2e9ef;border-radius:18px;padding:25px;box-shadow:0 12px 30px #19365512; }
#auth-screen .section-heading h1,#auth-screen .section-heading h2 { color:#17365f !important;font-size:30px !important;font-weight:850 !important;letter-spacing:-.5px; }
#auth-screen .section-heading p { color:#405570 !important;font-size:14px !important;line-height:1.65 !important;opacity:1 !important; }
#auth-screen .section-eyebrow { color:#0879b5 !important;font-weight:850 !important; }
#auth-screen .prose,#auth-screen .prose p,#auth-screen .prose strong,#auth-screen .prose li { color:#344b66 !important;opacity:1 !important;font-size:13px !important;line-height:1.6 !important; }
#auth-screen label,#auth-screen label span { color:#17365f !important;font-weight:750 !important; }
#auth-screen input { color:#17365f !important; }
#auth-screen input::placeholder { color:#687b95 !important;opacity:1 !important; }
#auth-screen .auth-fields,#auth-screen #auth-fields { --block-background-fill:#eaf4ff;--background-fill-secondary:#eaf4ff;padding:12px !important;border:1px solid #d3e4f7 !important;border-radius:12px !important;background:#eaf4ff !important;background-color:#eaf4ff !important;box-shadow:none !important; }
#auth-screen #auth-fields > div,#auth-screen #auth-fields .wrap { background:transparent !important;box-shadow:none !important; }
#auth-screen #auth-fields [data-testid]:not(input):not(textarea) { background-color:#eaf4ff !important;box-shadow:none !important; }
#auth-screen #auth-fields input,#auth-screen #auth-fields textarea { background:#fff !important;background-color:#fff !important;color:#17365f !important;-webkit-text-fill-color:#17365f !important;border:1px solid #c5d8ef !important;opacity:1 !important;box-shadow:0 2px 6px #17365f0d !important; }
#auth-screen #auth-fields input::placeholder { color:#687b95 !important;-webkit-text-fill-color:#687b95 !important;opacity:1 !important; }
#buyer-dashboard { max-width:1440px;margin:0 auto; }
#admin-dashboard { max-width:1500px;margin:20px auto;background:#f5f7fa; }
#admin-workspace { max-width:1200px;margin:20px auto;background:#f5f7fa; }
#buyer-dashboard .prose,#buyer-dashboard .prose p,#buyer-dashboard .prose strong,#buyer-dashboard .prose li,
#admin-dashboard .prose,#admin-dashboard .prose p,#admin-dashboard .prose strong,#admin-dashboard .prose li { color:#263e5b !important;opacity:1 !important; }
#buyer-dashboard h1,#buyer-dashboard h2,#buyer-dashboard h3,#buyer-dashboard label,
#admin-dashboard h1,#admin-dashboard h2,#admin-dashboard h3,#admin-dashboard label { color:#17365f !important; }
#buyer-dashboard small,#admin-dashboard small { color:#526780 !important; }
#admin-dashboard h1,#admin-dashboard h2,#admin-dashboard h3,#admin-order-form h2 { color:#17365f !important; }
#admin-dashboard p,#admin-dashboard .prose,#auth-screen .prose { color:#405570 !important; }
#admin-dashboard label,#admin-dashboard label span,#admin-order-form label,#admin-order-form label span { color:#17365f !important;font-weight:750 !important; }
#admin-dashboard input,#admin-dashboard textarea,#admin-dashboard select,#admin-order-form input,#admin-order-form textarea,#admin-order-form select { color:#17365f !important;background:#fff !important; }
#admin-dashboard input::placeholder,#admin-dashboard textarea::placeholder,#admin-order-form input::placeholder,#admin-order-form textarea::placeholder { color:#687b95 !important;opacity:1 !important; }
#admin-dashboard button:not(.primary) { color:#17365f !important; }
#admin-dashboard .logout-icon button,#buyer-dashboard .logout-icon button { color:#fff !important; }
.buyer-dashboard-topbar,.admin-dashboard-topbar { display:flex;align-items:center;justify-content:space-between;gap:16px;margin:5px 0 18px; }
.buyer-dashboard-topbar > *, .admin-dashboard-topbar > * { margin:0 !important; }
.buyer-dashboard-topbar .prose h3 { color:#17365f !important;margin:0 !important; }
.admin-dashboard-title { text-align:left; }
.admin-dashboard-title .section-eyebrow { color:#087fb9;font-size:11px; }
.admin-dashboard-title h1 { color:#17365f;font-size:32px;margin:5px 0; }
.admin-dashboard-title p { color:#405570;font-size:14px;margin:0; }
.logout-icon button { min-width:94px !important;width:auto !important;height:44px !important;padding:0 16px !important;border-radius:11px !important;background:#c62828 !important;color:white !important;font-size:14px !important;font-weight:800 !important;box-shadow:0 5px 14px #9f202033 !important; }
.logout-icon:hover { transform:translateY(-1px); }
.logout-icon:hover button { background:#a91f1f !important; }
#admin-order-form { position:relative;isolation:isolate;max-width:none;margin:24px 0;padding:22px 24px 24px;overflow:hidden;background:radial-gradient(ellipse at 2% 14%,#c8e2ff 0,transparent 18%),radial-gradient(ellipse at 98% 82%,#d4e8ff 0,transparent 23%),linear-gradient(135deg,#f1f7ff,#e5f1ff 52%,#f5faff);border:1px solid #c5dbf5;border-radius:24px;box-shadow:0 16px 36px #17477b1b; }
#admin-order-form > .wrap { position:relative;z-index:1; }
.order-form-heading { position:relative;display:flex;align-items:center;gap:18px;min-height:92px;margin:-2px 0 15px;padding:0 20px;overflow:hidden; }
.order-form-heading::before,.order-form-heading::after { content:"✦";position:absolute;color:#69b3ff;font-size:28px;opacity:.7; }
.order-form-heading::before { left:39%;top:10px; }
.order-form-heading::after { right:24%;top:4px;font-size:21px; }
.order-art-left { flex:none;width:104px;height:82px;display:grid;place-items:center; }
.order-art-left svg { width:78px;height:78px;filter:drop-shadow(0 8px 8px #3179be35); }
.order-art-right { position:absolute;right:18px;top:0;width:125px;height:90px;opacity:.78; }
.order-art-right svg { width:100%;height:100%;filter:drop-shadow(0 7px 7px #3179be25); }
.order-form-heading h2 { margin:0 0 4px !important;font-size:27px !important;letter-spacing:-.7px;color:#17365f !important; }
.order-form-heading p { margin:0 !important;font-size:15px !important;color:#304966 !important; }
.order-fields-grid { align-items:stretch !important;gap:24px !important; }
.order-fields-grid > .order-field-column { gap:14px !important;min-width:0 !important; }
.order-field-column > .order-field { padding:0 !important; }
.order-field { gap:0 !important;overflow:hidden;background:#e7f1ff;border:1px solid #cadcf3;border-radius:16px;box-shadow:0 8px 18px #1d5e9b14; }
.order-field-title { display:flex;align-items:center;gap:13px;min-height:52px;padding:0 17px;background:linear-gradient(105deg,#1a365f,#284b78);color:#fff;font-size:16px;font-weight:800;letter-spacing:-.15px; }
.order-field-title svg { flex:none;width:25px;height:25px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round; }
#admin-order-form .order-control { padding:0 10px 10px !important;background:#e7f1ff !important; }
#admin-order-form .order-control .wrap { gap:0 !important;background:transparent !important; }
#admin-order-form .order-control input,#admin-order-form .order-control textarea,#admin-order-form .order-control [role="combobox"] { min-height:54px;border:1px solid #c4d9f2 !important;border-radius:0 0 16px 16px !important;padding:12px 15px !important;background:linear-gradient(180deg,#fff,#f9fcff) !important;color:#19375e !important;font-size:16px !important;font-weight:600 !important;box-shadow:0 7px 13px #2c68a11c; }
#admin-order-form .order-control input,#admin-order-form .order-control textarea,#admin-order-form .order-control [role="combobox"] { border-radius:14px !important; }
#admin-order-form .order-control input::placeholder,#admin-order-form .order-control textarea::placeholder { color:#73849b !important;opacity:1 !important;font-weight:500 !important; }
#admin-order-form .order-notes textarea { min-height:60px !important;border-radius:0 0 15px 15px !important; }
#admin-order-form .order-payment-status { padding:7px 10px 11px !important;background:#e7f1ff !important; }
#admin-order-form .order-payment-status .wrap { display:flex !important;flex-direction:row !important;align-items:center;gap:12px !important;padding:1px 0 !important;flex-wrap:wrap !important; }
#admin-order-form .order-payment-status label { display:flex !important;align-items:center;gap:9px !important;min-width:125px;padding:11px 17px !important;border:1px solid #c4d8f2 !important;border-radius:999px !important;background:#edf5ff !important;color:#19375e !important;font-size:15px !important;font-weight:750 !important;box-shadow:0 4px 11px #2c68a114; }
#admin-order-form .order-payment-status label:has(input:checked) { background:linear-gradient(105deg,#177fd0,#278fe0) !important;border-color:#1680d4 !important;color:#fff !important; }
#admin-order-form .order-payment-status input[type="radio"] { width:19px !important;height:19px !important;margin:0 !important;accent-color:#fff; }
#admin-order-form .order-save button { width:100%;min-height:62px;border-radius:17px !important;background:linear-gradient(100deg,#39a8ef,#0868cb) !important;color:white !important;font-size:18px !important;font-weight:850 !important;box-shadow:0 10px 18px #1265ad3d !important; }
.order-data-panel { margin:22px 0;padding:0 12px 12px;overflow:hidden;border:1px solid #bfd7f5;border-radius:22px;background:linear-gradient(135deg,#eaf4ff,#f8fbff);box-shadow:0 12px 28px #17477b18; }
.order-data-heading { display:flex;align-items:center;gap:13px;margin:0 -12px 0;padding:15px 20px;background:linear-gradient(110deg,#193861,#0f2c51);color:#fff;font-size:17px;font-weight:850;border-radius:20px 20px 0 0; }
.order-data-heading svg { width:26px;height:26px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round; }
#admin-service-catalog { margin-top:0;overflow:hidden;border:1px solid #c7dbf2;border-radius:0 0 16px 16px;background:#fff;box-shadow:0 7px 15px #1b4e8317; }
#admin-service-catalog table thead { background:#dceaff !important;color:#17365f !important; }
#admin-service-catalog th { color:#17365f !important;background:#dceaff !important; }
#admin-service-catalog td { color:#243c5a !important;background:#f9fcff !important; }
#admin-service-catalog td,#admin-service-catalog th { border-color:#c7dbf2 !important; }
#admin-service-catalog table tbody tr:nth-child(even) td { background:#eef5ff !important; }
#admin-dashboard .order-section-title { color:#17365f !important;font-size:22px !important;font-weight:850 !important;margin:25px 0 10px !important; }
#admin-order-form .order-save button:hover { background:linear-gradient(100deg,#248cdb,#0758b0) !important; }
#metric-total,#metric-active,#metric-ready,#metric-revenue { background:white !important;border:1px solid #e1e8ef !important;border-radius:15px !important;padding:13px !important;box-shadow:0 5px 16px #1936550b !important; }
#metric-total label,#metric-active label,#metric-ready label,#metric-revenue label { color:#405570 !important;font-size:12px !important;font-weight:750 !important; }
#metric-total input,#metric-active input,#metric-ready input,#metric-revenue input { color:#126da7 !important;background:white !important;border:0 !important;font-size:24px !important;font-weight:850 !important; }
#recent-orders { overflow:hidden;background:white !important;border:1px solid #e1e8ef !important;border-radius:14px !important; }
thead,th { background:#dbeafe !important;color:#17365f !important;font-weight:800 !important; }
td,th { color:#243c5a !important;border-color:#cad9e8 !important;padding:10px 12px !important; }
input,textarea,select { background:white !important;color:#203650 !important;border-color:#c6d4e2 !important;border-radius:10px !important; }
# Kontras final untuk komponen Gradio yang memakai warna/opacity bawaan tema.
# Teks hero berada di atas bidang gelap, jadi harus putih; teks dashboard tetap navy gelap.
#buyer-dashboard .hero-title { color:#fff !important; }
#buyer-dashboard .hero-title span { color:#79dce8 !important; }
#buyer-dashboard .hero-description { color:#e4edf8 !important; }
#buyer-dashboard .hero-kicker { color:#a8f0f1 !important; }
#buyer-dashboard .hero-secondary { color:#fff !important; }
/* Selector langsung mengalahkan warna heading umum pada dashboard. */
#hero h1.hero-title { color:#fff !important;-webkit-text-fill-color:#fff !important;opacity:1 !important; }
#hero h1.hero-title span { color:#79dce8 !important;-webkit-text-fill-color:#79dce8 !important; }
#hero .hero-description { color:#eaf2fb !important;-webkit-text-fill-color:#eaf2fb !important;opacity:1 !important;font-weight:500 !important; }
#hero .hero-kicker { color:#a8f0f1 !important;-webkit-text-fill-color:#a8f0f1 !important; }
#hero .hero-secondary { color:#fff !important;-webkit-text-fill-color:#fff !important; }
#buyer-logout,#admin-logout,button#buyer-logout,button#admin-logout,
#buyer-logout button,#admin-logout button,.logout-icon,.logout-icon button { background:#c62828 !important;color:#fff !important;border-color:#b71c1c !important; }
#buyer-logout:hover,#admin-logout:hover,#buyer-logout:hover button,#admin-logout:hover button,.logout-icon:hover,.logout-icon:hover button { background:#a91f1f !important;color:#fff !important; }
#admin-refresh,#admin-refresh button { background:#147fba !important;color:#fff !important;border-color:#147fba !important;font-weight:800 !important; }
#admin-refresh:hover,#admin-refresh:hover button { background:#0e6597 !important;color:#fff !important; }
#metric-total input,#metric-active input,#metric-ready input,#metric-revenue input,
#metric-total input:disabled,#metric-active input:disabled,#metric-ready input:disabled,#metric-revenue input:disabled { color:#123b67 !important;-webkit-text-fill-color:#123b67 !important;opacity:1 !important;font-weight:850 !important; }
#metric-total label,#metric-active label,#metric-ready label,#metric-revenue label { color:#304966 !important; }
#admin-dashboard .prose,#admin-dashboard .prose p,#admin-dashboard .prose strong,
#buyer-dashboard .prose,#buyer-dashboard .prose p,#buyer-dashboard .prose strong { color:#263e5b !important;opacity:1 !important; }
.metrics-grid { display:grid !important;grid-template-columns:repeat(4,minmax(0,1fr)) !important;gap:14px !important;margin:14px 0 10px !important; }
.metric-card { min-height:92px !important;display:flex !important;flex-direction:row !important;align-items:center !important;gap:13px !important;padding:14px !important;border:1px solid #d7e7f8 !important;border-radius:18px !important;box-shadow:0 8px 19px #28578316 !important;overflow:hidden; }
.metric-card > .wrap { width:100% !important;display:flex !important;flex-direction:row !important;align-items:center !important;gap:13px !important; }
.metric-card-blue { background:linear-gradient(135deg,#fff 35%,#edf5ff) !important; }
.metric-card-sky { background:linear-gradient(135deg,#fff 35%,#e8f4ff) !important; }
.metric-card-mint { background:linear-gradient(135deg,#fff 35%,#e8faf6) !important; }
.metric-card-lilac { background:linear-gradient(135deg,#fff 35%,#f1efff) !important; }
.metric-icon { width:48px;height:48px;flex:none;display:grid;place-items:center;border-radius:50%;background:#dceeff;color:#1478d0;box-shadow:0 4px 10px #2366a51c; }
.metric-icon svg { width:25px;height:25px;fill:none;stroke:currentColor;stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round; }
.metric-card-mint .metric-icon { background:#c9f2e9;color:#17a58e; }
.metric-card-lilac .metric-icon { background:#e2ddff;color:#6654cc; }
.metric-copy { min-width:0 !important;gap:2px !important; }
.metric-title { color:#183860;font-size:13px;font-weight:800;line-height:1.3; }
#metric-total,#metric-active,#metric-ready,#metric-revenue { width:100% !important;min-width:0 !important;background:transparent !important;border:0 !important;padding:0 !important;box-shadow:none !important; }
#metric-total input,#metric-active input,#metric-ready input,#metric-revenue input,
#metric-total input:disabled,#metric-active input:disabled,#metric-ready input:disabled,#metric-revenue input:disabled { min-height:34px !important;padding:0 !important;border:0 !important;background:transparent !important;color:#102e56 !important;-webkit-text-fill-color:#102e56 !important;opacity:1 !important;font-size:27px !important;line-height:1 !important;font-weight:900 !important;box-shadow:none !important; }
#admin-refresh,#admin-refresh button { width:100% !important;min-height:42px !important;border-radius:12px !important; }
.recent-orders-panel { margin-top:18px !important; }
.data-panel-header { display:flex !important;align-items:center !important;gap:10px !important;margin:0 -12px !important;padding:0 15px !important;background:linear-gradient(105deg,#163a70,#204b86) !important;border-radius:20px 20px 0 0 !important; }
.data-panel-header .order-data-heading { flex:1 !important;margin:0 !important;padding:14px 6px !important;background:transparent !important;border-radius:0 !important; }
#admin-refresh,#admin-refresh button { width:42px !important;min-width:42px !important;height:36px !important;min-height:36px !important;padding:0 !important;border-radius:10px !important;background:#2c69b7 !important;color:#fff !important;border:1px solid #8bb8ec !important;font-size:23px !important;line-height:1 !important; }
#admin-refresh:hover,#admin-refresh:hover button { background:#367dd2 !important;color:#fff !important; }
#admin-refresh button { box-shadow:none !important; }
#admin-service-catalog,#recent-orders { border-radius:0 0 15px 15px !important; }
#admin-service-catalog table,#recent-orders table { width:100% !important;border-collapse:separate !important;border-spacing:0 !important; }
#admin-service-catalog th,#recent-orders th { padding:11px 13px !important;background:#e3efff !important;color:#17365f !important;font-weight:850 !important;border-color:#cbdcf2 !important; }
#admin-service-catalog td,#recent-orders td { padding:10px 13px !important;background:#fff !important;color:#1c3554 !important;border-color:#d8e4f2 !important;font-weight:600 !important; }
#admin-service-catalog tbody tr:nth-child(even) td,#recent-orders tbody tr:nth-child(even) td { background:#f3f8ff !important; }
#admin-service-catalog,#recent-orders { background:transparent !important;color:#17365f !important; }
#admin-service-catalog .custom-table-scroll,#recent-orders .custom-table-scroll { width:100%;overflow-x:auto;border:1px solid #cbdcf2;border-radius:0 0 15px 15px;background:#fff; }
.custom-dashboard-table { width:100%;min-width:720px;border-collapse:separate !important;border-spacing:0 !important;background:#fff !important;color:#18365d !important;font-family:inherit !important;font-size:13px !important; }
.custom-dashboard-table th { padding:11px 13px !important;text-align:left !important;white-space:nowrap;background:#e2efff !important;color:#17365f !important;border-right:1px solid #ccdef2 !important;border-bottom:1px solid #ccdef2 !important;font-weight:850 !important; }
.custom-dashboard-table td { padding:9px 13px !important;text-align:left !important;white-space:nowrap;background:#fff !important;color:#1d3553 !important;border-right:1px solid #e0e9f4 !important;border-bottom:1px solid #e0e9f4 !important;font-weight:600 !important; }
.custom-dashboard-table tbody tr:nth-child(even) td { background:#f3f8ff !important; }
.custom-dashboard-table tbody tr:last-child td { border-bottom:0 !important; }
.custom-dashboard-table th:last-child,.custom-dashboard-table td:last-child { border-right:0 !important; }
.custom-dashboard-table .order-code-cell { color:#173e70 !important;font-weight:800 !important; }
.custom-dashboard-table .order-total-cell { color:#163b67 !important;font-weight:850 !important; }
.table-pill { display:inline-flex;align-items:center;justify-content:center;min-width:78px;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:850; }
.table-pill.progress { background:#dbeaff;color:#1269c3; }
.table-pill.ready { background:#d9f5ea;color:#087c61; }
.table-pill.done { background:#e8e7ff;color:#5544b7; }
.table-pill.cancelled { background:#ffe1e1;color:#aa2828; }
.table-pill.paid { background:#d9f5e6;color:#147348; }
.table-pill.unpaid { background:#ffebce;color:#a9570a; }
.service-name-cell { color:#17365f;font-weight:800; }
.metrics-grid > #metric-total,.metrics-grid > #metric-active,.metrics-grid > #metric-ready,.metrics-grid > #metric-revenue { flex:1 1 0;min-width:0; }
.metric-tile { min-height:86px;display:flex;align-items:center;gap:13px;padding:14px 17px;border:1px solid #d4e3f5;border-radius:17px;box-shadow:0 8px 20px #1e4a7615; }
.metric-blue { background:linear-gradient(135deg,#fff 0%,#edf5ff 100%); }
.metric-sky { background:linear-gradient(135deg,#fff 0%,#eaf5ff 100%); }
.metric-mint { background:linear-gradient(135deg,#fff 0%,#e9faf6 100%); }
.metric-lilac { background:linear-gradient(135deg,#fff 0%,#f1efff 100%); }
.metric-tile-icon { width:46px;height:46px;flex:none;display:grid;place-items:center;border-radius:50%;background:#d9ebff;color:#1675cf; }
.metric-tile-icon svg { width:24px;height:24px;fill:none;stroke:#1675cf !important;color:#1675cf !important;stroke-width:2.1;stroke-linecap:round;stroke-linejoin:round; }
.metric-mint .metric-tile-icon { background:#c9f1e9; }
.metric-mint .metric-tile-icon svg { stroke:#159984 !important;color:#159984 !important; }
.metric-lilac .metric-tile-icon { background:#e3ddff; }
.metric-lilac .metric-tile-icon svg { stroke:#6554c8 !important;color:#6554c8 !important; }
.metric-tile-title { margin-bottom:3px;color:#17365f !important;font-size:13px;font-weight:800; }
.metric-tile-value { color:#102e56 !important;font-size:27px;font-weight:900;line-height:1.1; }
#buyer-order-form { position:relative;isolation:isolate;max-width:1120px;margin:0 auto 34px;padding:18px 20px 20px;overflow:hidden;border:1px solid #c5ddfb;border-radius:22px;background:radial-gradient(ellipse at 0 0,#d9ebff 0,transparent 36%),radial-gradient(ellipse at 100% 0,#d3e9ff 0,transparent 31%),linear-gradient(145deg,#f9fcff,#eaf4ff 60%,#f5faff);box-shadow:0 14px 30px #1e57931b; }
.buyer-order-heading { position:relative;display:flex;align-items:center;gap:12px;min-height:62px;margin:0 0 12px;padding:0 6px; }
.buyer-order-art { flex:none;width:55px;height:55px;display:grid;place-items:center; }
.buyer-order-art svg { width:52px;height:52px;filter:drop-shadow(0 4px 5px #2166a52a); }
.buyer-order-heading h2 { margin:0 0 3px !important;color:#173d73 !important;font-size:21px !important;font-weight:900 !important;letter-spacing:-.3px; }
.buyer-order-heading p { margin:0 !important;color:#385a83 !important;font-size:12px !important;font-weight:650 !important; }
.buyer-order-sparkle { margin-left:4px;color:#64aaf2;font-size:24px; }
.buyer-order-fields { gap:14px !important; }
.buyer-order-fields > .order-field-column { gap:7px !important; }
#buyer-order-form .order-field { gap:0 !important;overflow:hidden;padding:0 !important;background:#e6f1ff !important;border:1px solid #c5daf3 !important;border-radius:12px !important;box-shadow:0 4px 10px #1a548f14 !important; }
#buyer-order-form .order-field-title { min-height:31px;padding:0 10px;background:linear-gradient(100deg,#19385f,#254a79);color:#fff !important;font-size:12px;font-weight:800;gap:8px; }
#buyer-order-form .order-field-title svg { width:17px;height:17px;stroke:#fff !important;color:#fff !important; }
#buyer-order-form .order-control { padding:4px 6px 6px !important;background:transparent !important; }
#buyer-order-form .order-control input,#buyer-order-form .order-control textarea,#buyer-order-form .order-control [role="combobox"] { width:100%;min-height:36px;padding:7px 11px !important;border:1px solid #cfdef0 !important;border-radius:9px !important;background:#fff !important;color:#19375e !important;-webkit-text-fill-color:#19375e !important;font-size:13px !important;font-weight:650 !important;box-shadow:0 3px 7px #23527e12 !important;opacity:1 !important; }
#buyer-order-form .order-control input::placeholder,#buyer-order-form .order-control textarea::placeholder { color:#7288a5 !important;-webkit-text-fill-color:#7288a5 !important;opacity:1 !important;font-weight:500 !important; }
#buyer-order-form .order-save button,#buyer-submit { width:100% !important;min-height:47px !important;margin-top:10px;border:0 !important;border-radius:13px !important;background:linear-gradient(100deg,#21a6ed,#0875dc) !important;color:#fff !important;font-size:15px !important;font-weight:900 !important;box-shadow:0 7px 14px #1477c638 !important; }
#buyer-order-form .order-save button:hover,#buyer-submit:hover { background:linear-gradient(100deg,#118bd5,#075fb9) !important; }
#buyer-order-form #buyer-order-result { color:#17365f !important; }
#buyer-track { max-width:1120px;margin:18px auto 40px;padding:0 0 13px;overflow:hidden;border:1px solid #c5def9;border-radius:20px;background:linear-gradient(145deg,#f8fbff,#eaf4ff);box-shadow:0 12px 25px #1a548f18; }
.track-heading { position:relative;display:flex;align-items:center;gap:12px;min-height:48px;padding:0 20px;overflow:hidden;background:linear-gradient(105deg,#173961,#23508b);color:#fff; }
.track-heading h2 { z-index:1;margin:0 !important;color:#fff !important;font-size:15px !important;font-weight:850 !important; }
.track-search-icon { z-index:1;color:#fff;font-size:32px;line-height:1; }
.track-art { position:absolute;right:20px;top:-9px;color:#80bdff;font-size:26px;letter-spacing:7px;opacity:.85; }
.track-fields { gap:14px !important;padding:14px 16px 6px !important; }
.track-field { gap:3px !important;min-width:0 !important; }
.track-field .order-field-title { min-height:22px;padding:0 4px;background:transparent !important;color:#173d73 !important;font-size:12px;font-weight:850;gap:7px; }
.track-field .order-field-title svg { width:17px;height:17px;stroke:#1764ac !important;color:#1764ac !important; }
.track-label { display:flex;align-items:center;gap:8px;min-height:22px;padding:0 4px;color:#173d73 !important;-webkit-text-fill-color:#173d73 !important;font-size:12px;font-weight:850;opacity:1 !important; }
.track-label svg { width:17px;height:17px;flex:none;stroke:#1764ac !important;color:#1764ac !important; }
.track-control { padding:0 !important;background:transparent !important; }
.track-control input { min-height:38px !important;padding:8px 12px !important;border:1px solid #d0e0f3 !important;border-radius:11px !important;background:#fff !important;color:#17365f !important;-webkit-text-fill-color:#17365f !important;font-size:13px !important;box-shadow:0 3px 9px #1c548a12 !important;opacity:1 !important; }
.track-control input::placeholder { color:#7388a3 !important;-webkit-text-fill-color:#7388a3 !important;opacity:1 !important; }
#track-submit,#track-submit button { width:calc(100% - 32px) !important;margin:0 16px 9px !important;min-height:42px !important;border-radius:12px !important;background:linear-gradient(100deg,#16a7ea,#0879e3) !important;color:#fff !important;font-size:15px !important;font-weight:900 !important;box-shadow:0 5px 11px #1577cb30 !important; }
.track-helper { display:flex;align-items:center;justify-content:center;gap:8px;min-height:30px;margin:0 16px 1px;padding:5px 10px;border:1px solid #c5def8;border-radius:9px;background:#dceeff;color:#244f7e;font-size:11px;font-weight:650;text-align:center; }
.track-helper span { width:16px;height:16px;display:grid;place-items:center;flex:none;border-radius:50%;background:#2c70b7;color:#fff;font-size:11px;font-weight:900; }
.track-code-reminder { margin:8px 16px 14px;padding:9px 12px;border:1px solid #f2cf75;border-radius:9px;background:#fff8df;color:#694b08;font-size:11px;font-weight:750;line-height:1.5;text-align:center; }
#buyer-track #track-result { margin:10px 16px 0 !important; }
.payment-guide-card { display:flex;align-items:center;justify-content:space-between;gap:22px;margin:13px 0 4px;padding:16px 18px;border:1px solid #bfd8f5;border-radius:15px;background:linear-gradient(120deg,#f7fbff,#eaf4ff);color:#17365f; }
.payment-guide-copy { min-width:0; }
.payment-guide-eyebrow { display:block;margin-bottom:4px;color:#1377b7;font-size:10px;font-weight:900;letter-spacing:1px; }
.payment-guide-card h3 { margin:0 0 5px;color:#17365f !important;font-size:16px !important;font-weight:850 !important; }
.payment-guide-card p { margin:0 0 6px;color:#38536f !important;font-size:12px !important;line-height:1.55 !important; }
.payment-guide-card small { display:block;color:#536d88 !important;font-size:11px !important;line-height:1.5 !important; }
.payment-qris-frame { flex:none;width:150px;height:150px;display:grid;place-items:center;padding:8px;border:1px solid #d4e2f2;border-radius:12px;background:#fff;box-shadow:0 4px 12px #19365512; }
.payment-qris-image { display:block;width:100%;height:100%;object-fit:contain;border-radius:6px; }
.payment-qris-missing { color:#8f2b2b;font-size:11px;text-align:center; }
.payment-guide-bank { flex-wrap:wrap; }
.bank-account-card { flex:none;min-width:230px;display:flex;flex-direction:column;gap:3px;padding:12px 15px;border:1px solid #cadcf1;border-radius:12px;background:#fff;box-shadow:0 4px 10px #1936550d; }
.bank-account-card span { color:#526780;font-size:11px;font-weight:750; }
.bank-account-card strong { color:#163b67;font-size:22px;letter-spacing:1px; }
.bank-account-card small { color:#38536f;font-size:12px;font-weight:700; }
.payment-guide-footnote { flex-basis:100%; }
.payment-guide-cash { display:block; }
.payment-guide-cash h3 { margin-bottom:4px; }
/* Bersihkan panel bawaan Gradio yang membungkus input, tetap simpan field putih. */
#buyer-order-form .order-field { background:#e6f1ff !important; }
#buyer-order-form .order-control,#buyer-order-form .order-control *,
#buyer-track .track-field,#buyer-track .track-control,#buyer-track .track-control * { background-color:#eaf4ff !important;box-shadow:none !important; }
#buyer-order-form .order-control input,#buyer-order-form .order-control textarea,
#buyer-order-form .order-control [role="combobox"],#buyer-track .track-control input { background:#fff !important;color:#19375e !important;-webkit-text-fill-color:#19375e !important;border-color:#c4d9f2 !important;opacity:1 !important; }
/* Dropdown menus can render in a portal outside the form; style the popup globally too. */
body [role="listbox"],body [role="listbox"] *,body [role="option"],
body .options,body .options *,body [data-testid*="dropdown"] li,
#buyer-order-form .order-control [role="listbox"],#buyer-order-form .order-control [role="listbox"] *,
#buyer-order-form .order-control [role="option"],#buyer-order-form .order-control li { background:#fff !important;color:#17365f !important;-webkit-text-fill-color:#17365f !important;opacity:1 !important; }
body [role="option"]:hover,body [role="option"][aria-selected="true"],body .options li:hover,
#buyer-order-form .order-control [role="option"]:hover { background:#dceeff !important;color:#102e56 !important;-webkit-text-fill-color:#102e56 !important; }
#buyer-dashboard #buyer-track .track-heading h2 { color:#fff !important;-webkit-text-fill-color:#fff !important;opacity:1 !important; }
#buyer-dashboard #buyer-track .track-heading .track-search-icon { color:#fff !important;-webkit-text-fill-color:#fff !important; }
#buyer-dashboard #buyer-order-form .order-field-title { color:#fff !important;-webkit-text-fill-color:#fff !important; }
#buyer-dashboard #buyer-order-form .order-field-title svg { stroke:#fff !important;color:#fff !important; }
#buyer-order-result:not(:has(.prose p)),#track-result:not(:has(.prose p)) { display:none !important; }
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
 #admin-order-form { padding:16px; }
 .order-fields-grid { flex-direction:column !important;gap:14px !important; }
 .order-form-heading { padding:0 5px;gap:8px; }
 .order-art-left { width:70px;height:72px; }
 .order-art-left svg { width:62px;height:62px; }
 .order-art-right { display:none; }
 .order-form-heading h2 { font-size:22px !important; }
 .metrics-grid { grid-template-columns:repeat(2,minmax(0,1fr)) !important; }
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
 .form-panel { padding:15px; }
 #admin-order-form { padding:14px; }
 .admin-dashboard-title h1 { font-size:25px; }
 .order-form-heading h2 { font-size:20px !important; }
 .metrics-grid { grid-template-columns:1fr !important; }
 .metric-card { min-height:76px !important; }
 #buyer-order-form { padding:13px; }
 .buyer-order-art { width:40px;height:45px; }
 .buyer-order-art svg { width:42px;height:42px; }
 .buyer-order-heading h2 { font-size:18px !important; }
 .buyer-order-sparkle { display:none; }
 .buyer-order-fields,.track-fields { flex-direction:column !important;gap:8px !important; }
 #buyer-track { margin:12px 4px 28px; }
 .track-heading { padding:0 13px; }
 .track-fields { padding:10px 10px 5px !important; }
 #track-submit,#track-submit button { width:calc(100% - 20px) !important;margin:0 10px 8px !important; }
 .track-helper { margin:0 10px; }
 .track-code-reminder { margin:8px 10px 12px; }
 .payment-guide-card { align-items:flex-start;flex-direction:column;gap:12px;padding:13px; }
 .payment-qris-frame { width:180px;height:180px;align-self:center; }
 .bank-account-card { width:100%;min-width:0; }
}
"""

with gr.Blocks(title="Laundry Halilintar") as demo:
    gr.HTML("<div id='brandbar'><div id='brand-lock'><div id='brand-mark'>✦</div><div><div id='brand-name'>LAUNDRY HALILINTAR</div><div id='brand-caption'>Perawatan pakaian yang lebih mudah</div></div></div><div id='brand-hours'>Senin—Minggu &nbsp;·&nbsp; 07.00—20.00</div></div>")
    admin_session = gr.State(False)
    buyer_session = gr.State(None)

    with gr.Column(elem_id="auth-screen", elem_classes=["form-panel"]) as auth_screen:
        gr.HTML("<div class='section-heading'><div class='section-eyebrow'>AKUN LAUNDRY HALILINTAR</div><h1>Masuk atau daftar</h1><p>Daftar reguler akan membuat akun pembeli. Akun admin masuk dengan email admin yang sudah terdaftar.</p></div>")
        with gr.Row(elem_id="auth-fields", elem_classes=["auth-fields"]):
            portal_email_input = gr.Textbox(label="Email", placeholder="email@contoh.com")
            portal_password_input = gr.Textbox(label="Password", type="password", placeholder="Minimal 8 karakter")
        with gr.Row():
            portal_login_button = gr.Button("Masuk", variant="primary")
            portal_register_button = gr.Button("Daftar sebagai pembeli")
        portal_status = gr.Markdown("Belum masuk. Daftar sebagai pembeli atau masuk dengan akun yang sudah terdaftar.")
        gr.Markdown("Admin: gunakan akun admin yang sudah dibuat di Supabase. Pendaftaran reguler hanya untuk pembeli.")

    with gr.Column(visible=False, elem_id="buyer-dashboard") as buyer_dashboard:
        with gr.Row(elem_classes=["buyer-dashboard-topbar"]):
            buyer_greeting = gr.Markdown(scale=1)
            buyer_logout_button = gr.Button("Log out", size="sm", scale=0, min_width=94, elem_id="buyer-logout", elem_classes=["logout-icon"])
        gr.HTML("<nav id='public-nav'><a class='nav-logo' href='#top'>HALILINTAR</a><div class='nav-links'><a href='#buyer-services'>LAYANAN</a><a href='#buyer-process'>CARA KERJA</a><a href='#buyer-track'>CEK PESANAN</a><a class='nav-cta' href='#buyer-order'>PESAN SEKARANG</a></div></nav>")
        gr.HTML("<section id='top'><div id='hero'><div class='hero-copy'><div class='hero-kicker'>LAUNDRY CARE, MADE SIMPLE</div><h1 class='hero-title'>Pakaian bersih,<br><span>hari lebih ringan.</span></h1><p class='hero-description'>Titipkan cucianmu kepada Laundry Halilintar. Kami bantu pakaian kembali bersih, rapi, dan siap menemani aktivitasmu.</p><div class='hero-actions'><a class='hero-button' href='#buyer-order'>Pesan laundry &nbsp;→</a><a class='hero-secondary' href='#buyer-services'>Lihat layanan</a></div></div>" + MACHINE_ART + "</div></section><div id='feature-strip'><div class='feature-card'><div class='feature-icon'>✧</div><div><strong>Penanganan teliti</strong><small>Pakaian dijaga dengan rapi</small></div></div><div class='feature-card'><div class='feature-icon'>◷</div><div><strong>Estimasi jelas</strong><small>Pantau status pesanan</small></div></div><div class='feature-card'><div class='feature-icon'>◇</div><div><strong>Pilihan praktis</strong><small>Layanan sesuai kebutuhan</small></div></div><div class='feature-card'><div class='feature-icon'>♡</div><div><strong>Mulai Rp7.000/kg</strong><small>Harga layanan reguler</small></div></div></div>")
        gr.HTML("<section id='buyer-services' class='section'><div class='section-heading'><div class='section-eyebrow'>LAYANAN KAMI</div><h2>Perawatan pas untuk pakaianmu</h2><p>Pilih layanan sesuai kebutuhan. Harga dan estimasi ditampilkan sebelum pesanan dikirim.</p></div>" + service_cards_markup() + "</section>")
        gr.HTML("<section id='buyer-process' class='section soft'><div class='section-heading'><div class='section-eyebrow'>MUDAH DAN PRAKTIS</div><h2>Proses dibuat sederhana</h2><p>Cukup beberapa langkah untuk menitipkan dan mengambil laundry.</p></div><div class='steps'><article class='step-card'><b>01 / PESAN</b><h3>Pilih layanan</h3><p>Isi data kontak, pilih layanan, dan masukkan berat cucianmu.</p></article><article class='step-card'><b>02 / PROSES</b><h3>Kami kerjakan</h3><p>Simpan kode pesanan. Admin memperbarui status saat cucian diproses.</p></article><article class='step-card'><b>03 / AMBIL</b><h3>Cucian siap</h3><p>Cek status dengan kode pesanan dan nomor WhatsApp terdaftar.</p></article></div></section>")
        gr.HTML("<section id='buyer-order' class='section'><div class='section-heading'><div class='section-eyebrow'>MULAI DARI SINI</div><h2>Pesan layanan laundry</h2><p>Kode pesanan muncul setelah pesanan berhasil dikirim.</p></div></section>")
        with gr.Column(elem_id="buyer-order-form", elem_classes=["buyer-order-panel"]):
            gr.HTML("""<div class='buyer-order-heading'><div class='buyer-order-art'><svg viewBox='0 0 72 72' aria-hidden='true'><rect x='15' y='8' width='43' height='56' rx='7' fill='#e7f2ff' stroke='#1761aa' stroke-width='3'/><path d='M25 8v-3h23v3M24 20h25M24 28h25M24 36h17M24 45h25' stroke='#2879c5' stroke-width='3' stroke-linecap='round'/><path d='M57 53h12M62 52V38a7 7 0 0 1 14 0v14M57 54l12-8 12 8' transform='translate(-6 -2)' fill='none' stroke='#2386df' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'/></svg></div><div><h2>Formulir pesanan</h2><p>Jam buka setiap hari, 07.00–20.00.</p></div><span class='buyer-order-sparkle'>✦</span></div>""")
            if not ADMIN_DB:
                gr.Markdown(f"Info: {ADMIN_DB_CONFIG_ERROR or 'pemesanan online perlu koneksi admin Supabase di file .env lokal.'}")
            with gr.Row(elem_classes=["order-fields-grid", "buyer-order-fields"]):
                with gr.Column(elem_classes=["order-field-column"]):
                    with gr.Column(elem_classes=["order-field"]):
                        gr.HTML(order_field_header("person", "Nama lengkap"))
                        buyer_name = gr.Textbox(show_label=False, placeholder="Nama kamu", elem_classes=["order-control"])
                    with gr.Column(elem_classes=["order-field"]):
                        gr.HTML(order_field_header("phone", "Nomor WhatsApp"))
                        buyer_phone = gr.Textbox(show_label=False, placeholder="08xxxxxxxxxx", elem_classes=["order-control"])
                    with gr.Column(elem_classes=["order-field"]):
                        gr.HTML(order_field_header("laundry", "Pilih layanan"))
                        buyer_service = gr.Dropdown(choices=service_choices(), show_label=False, elem_classes=["order-control"])
                with gr.Column(elem_classes=["order-field-column"]):
                    with gr.Column(elem_classes=["order-field"]):
                        gr.HTML(order_field_header("scale", "Perkiraan berat (kg)"))
                        buyer_weight = gr.Number(minimum=0.1, value=2, precision=2, show_label=False, placeholder="Contoh: 2", elem_classes=["order-control"])
                    with gr.Column(elem_classes=["order-field"]):
                        gr.HTML(order_field_header("payment", "Rencana pembayaran"))
                        buyer_payment = gr.Dropdown(["Tunai", "QRIS", "Transfer Bank"], value="Tunai", show_label=False, elem_classes=["order-control"])
                    with gr.Column(elem_classes=["order-field"]):
                        gr.HTML(order_field_header("notes", "Catatan khusus (opsional)"))
                        buyer_notes = gr.Textbox(show_label=False, lines=1, placeholder="Contoh: pakaian putih dipisah", elem_classes=["order-control"])
            payment_guidance = gr.HTML(payment_guidance_markup("Tunai"), elem_id="payment-guidance")
            buyer_submit = gr.Button("➤   Kirim pesanan", variant="primary", elem_id="buyer-submit", elem_classes=["order-save"])
            buyer_result = gr.Markdown(elem_id="buyer-order-result")
        with gr.Column(elem_id="buyer-track", elem_classes=["track-panel"]):
            gr.HTML("<div class='track-heading'><span class='track-search-icon'>⌕</span><h2>Cek Status Pesanan</h2><div class='track-art'>✦　◉</div></div>")
            with gr.Row(elem_classes=["track-fields"]):
                with gr.Column(elem_classes=["track-field"]):
                    gr.HTML(f"<div class='track-label'>{FORM_ICONS['data']}<span>Kode pesanan</span></div>")
                    track_code = gr.Textbox(show_label=False, placeholder="Masukkan kode pesanan...", elem_classes=["track-control"])
                with gr.Column(elem_classes=["track-field"]):
                    gr.HTML(f"<div class='track-label'>{FORM_ICONS['phone']}<span>Nomor WhatsApp</span></div>")
                    track_phone = gr.Textbox(show_label=False, placeholder="Masukkan nomor WhatsApp...", elem_classes=["track-control"])
            track_button = gr.Button("⌕   Cek status", variant="primary", elem_id="track-submit")
            gr.HTML("<div class='track-helper'><span>i</span>Masukkan kode pesanan atau nomor WhatsApp untuk melihat status pesanan Anda.</div>")
            gr.HTML("<div class='track-code-reminder'>⚠️ Penting: catat atau simpan kode pesanan setelah checkout. Kode ini diperlukan untuk mengecek status cucian dan membantu admin mencocokkan pembayaran.</div>")
            track_result = gr.Markdown(elem_id="track-result")
        gr.HTML("<div id='site-footer'>© 2026 Laundry Halilintar · Buka setiap hari, 07.00–20.00</div>")


    with gr.Column(visible=False, elem_id="admin-dashboard") as admin_workspace:
        with gr.Row(elem_classes=["admin-dashboard-topbar"]):
            gr.HTML("<div class='admin-dashboard-title'><div class='section-eyebrow'>PANEL PENGELOLAAN</div><h1>Dashboard admin</h1><p>Kelola transaksi, status cucian, dan pembayaran.</p></div>", scale=1, min_width=0)
            admin_logout_button = gr.Button("Log out", size="sm", scale=0, min_width=94, elem_id="admin-logout", elem_classes=["logout-icon"])
        with gr.Column(elem_id="admin-order-form"):
            gr.HTML("""<div class='order-form-heading'><div class='order-art-left'><svg viewBox='0 0 100 100' aria-hidden='true'><rect x='12' y='9' width='76' height='82' rx='12' fill='#fff' stroke='#70a9e8' stroke-width='4'/><rect x='18' y='16' width='64' height='13' rx='4' fill='#d9edff'/><circle cx='70' cy='22' r='3' fill='#2589d8'/><circle cx='78' cy='22' r='3' fill='#2589d8'/><circle cx='50' cy='59' r='25' fill='#d7efff' stroke='#398bd1' stroke-width='5'/><circle cx='50' cy='59' r='17' fill='url(#washerBlue)'/><path d='M30 82h40' stroke='#c1ddfa' stroke-width='5' stroke-linecap='round'/><defs><radialGradient id='washerBlue'><stop stop-color='#b6f3f5'/><stop offset='.65' stop-color='#65c3dc'/><stop offset='1' stop-color='#2780c8'/></radialGradient></defs></svg></div><div class='order-title-copy'><h2>Form Pesanan Laundry <span>✦</span></h2><p>Isi data pesanan dengan lengkap dan benar</p></div><div class='order-art-right'><svg viewBox='0 0 130 90' aria-hidden='true'><path d='M36 27h58M47 26v-8a13 13 0 0 1 26 0v8' fill='none' stroke='#438fdb' stroke-width='6' stroke-linecap='round'/><path d='M30 32h70l-5 11H35z' fill='#fdfefe' stroke='#70a9e8' stroke-width='3'/><path d='M56 47l-9 28h35l-9-28z' fill='#eef7ff' stroke='#86b8e8' stroke-width='3'/><path d='M52 73h34v9H52z' rx='4' fill='#4c9ade'/><path d='M109 13l3 8 8 3-8 3-3 8-3-8-8-3 8-3z' fill='#67b4ff'/></svg></div></div>""")
            with gr.Row(elem_classes=["order-fields-grid"]):
                with gr.Column(elem_classes=["order-field-column"]):
                    with gr.Column(elem_classes=["order-field"]):
                        gr.HTML(order_field_header("person", "Nama pelanggan"))
                        customer_name = gr.Textbox(show_label=False, placeholder="Masukkan nama pelanggan...", elem_classes=["order-control"])
                    with gr.Column(elem_classes=["order-field"]):
                        gr.HTML(order_field_header("phone", "Nomor WhatsApp"))
                        customer_phone = gr.Textbox(show_label=False, placeholder="Masukkan nomor WhatsApp...", elem_classes=["order-control"])
                    with gr.Column(elem_classes=["order-field"]):
                        gr.HTML(order_field_header("laundry", "Layanan"))
                        service_select = gr.Dropdown(choices=service_choices(), show_label=False, elem_classes=["order-control"])
                with gr.Column(elem_classes=["order-field-column"]):
                    with gr.Column(elem_classes=["order-field"]):
                        gr.HTML(order_field_header("scale", "Berat (kg)"))
                        weight_input = gr.Number(minimum=0.1, value=1, precision=2, show_label=False, placeholder="Masukkan berat...", elem_classes=["order-control"])
                    with gr.Column(elem_classes=["order-field"]):
                        gr.HTML(order_field_header("payment", "Metode pembayaran"))
                        payment_select = gr.Dropdown(["Belum dibayar", "Tunai", "QRIS", "Transfer Bank"], value="Belum dibayar", show_label=False, elem_classes=["order-control"])
                    with gr.Column(elem_classes=["order-field"]):
                        gr.HTML(order_field_header("status", "Status pembayaran"))
                        paid_select = gr.Radio(["Belum Lunas", "Lunas"], value="Belum Lunas", show_label=False, elem_classes=["order-payment-status"])
            with gr.Column(elem_classes=["order-field", "order-notes"]):
                gr.HTML(order_field_header("notes", "Catatan cucian"))
                notes_input = gr.Textbox(show_label=False, lines=2, placeholder="Tambahkan catatan khusus...", elem_classes=["order-control"])
            create_button = gr.Button("➤   Simpan pesanan", variant="primary", elem_id="admin-submit", elem_classes=["order-save"])
            order_notice = gr.Markdown()
        with gr.Column(elem_classes=["order-data-panel"]):
            with gr.Row(elem_classes=["data-panel-header"]):
                gr.HTML(f"<div class='order-data-heading'>{FORM_ICONS['data']}<span>Data Pesanan</span></div>")
                admin_refresh = gr.Button("↻", elem_id="admin-refresh", elem_classes=["table-refresh"])
            gr.HTML(render_service_table(), elem_id="admin-service-catalog")
        with gr.Row(elem_classes=["metrics-grid"]):
            total_card = gr.HTML(render_metric_card("Total pesanan", 0, "cart", "blue"), elem_id="metric-total")
            active_card = gr.HTML(render_metric_card("Sedang berjalan", 0, "calendar", "sky"), elem_id="metric-active")
            ready_card = gr.HTML(render_metric_card("Siap diambil", 0, "check", "mint"), elem_id="metric-ready")
            revenue_card = gr.HTML(render_metric_card("Pembayaran lunas", "Rp0", "shirt", "lilac"), elem_id="metric-revenue")
        with gr.Column(elem_classes=["order-data-panel", "recent-orders-panel"]):
            gr.HTML(f"<div class='order-data-heading'>{FORM_ICONS['data']}<span>Pesanan terbaru</span></div>")
            orders_table = gr.HTML(render_orders_table([]), elem_id="recent-orders")
    portal_outputs = [portal_status, admin_session, buyer_session, auth_screen, buyer_dashboard, admin_workspace,
                     total_card, active_card, ready_card, revenue_card, orders_table, buyer_greeting]
    portal_login_button.click(login_from_portal, [portal_email_input, portal_password_input], portal_outputs)
    portal_register_button.click(register_from_portal, [portal_email_input, portal_password_input], portal_outputs)
    buyer_logout_button.click(logout_from_portal, outputs=portal_outputs)
    admin_logout_button.click(logout_from_portal, outputs=portal_outputs)
    buyer_payment.change(payment_guidance_markup, inputs=buyer_payment, outputs=payment_guidance)
    admin_refresh.click(refresh_dashboard_for_admin, inputs=[admin_session], outputs=[total_card, active_card, ready_card, revenue_card, orders_table])
    create_button.click(create_order, [customer_name, customer_phone, service_select, weight_input, payment_select, paid_select, notes_input, admin_session], [order_notice, total_card, active_card, ready_card, revenue_card, orders_table, service_select])
    buyer_submit.click(create_buyer_order, [buyer_name, buyer_phone, buyer_service, buyer_weight, buyer_payment, buyer_notes, buyer_session], outputs=buyer_result)
    track_button.click(track_buyer_order, [track_code, track_phone], outputs=track_result)
if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(primary_hue="sky", secondary_hue="blue", neutral_hue="slate"), css=CSS)


