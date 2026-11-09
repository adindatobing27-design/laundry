import json
import os
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


def load_local_faqs():
    with DATA_FILE.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def load_knowledge():
    """Membaca FAQ/layanan publik Supabase; fallback ke FAQ lokal."""
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        return load_local_faqs(), []
    try:
        from supabase import create_client

        client = create_client(url, key)
        faqs = client.table("faqs").select("question, answer").eq("is_active", True).execute().data
        services = (
            client.table("services")
            .select("name, description, price_per_kg, estimated_hours")
            .eq("is_active", True)
            .execute()
            .data
        )
        return faqs or load_local_faqs(), services or []
    except Exception as error:
        print(f"Supabase belum dapat dibaca; memakai FAQ lokal ({type(error).__name__}).")
        return load_local_faqs(), []


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
    for item in SERVICES:
        price = item.get("price_per_kg")
        price_text = f"Rp{price}/kg" if price is not None else "harga belum dicantumkan"
        hours = item.get("estimated_hours")
        time_text = f"estimasi {hours} jam" if hours is not None else "estimasi belum dicantumkan"
        lines.append(f"Layanan: {item['name']}. {item.get('description', '')} Harga: {price_text}. {time_text}.")
    return "\n".join(lines)


def respond(message, history):
    system_text = (
        "Kamu asisten laundry yang ramah. Jawab singkat dalam bahasa Indonesia dan gunakan hanya konteks ini. "
        "Jika informasi tidak tersedia, katakan belum tahu dan sarankan menghubungi admin. Jangan mengarang "
        "harga, jam buka, atau status pesanan.\n\nInformasi laundry:\n" + build_context()
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
    answer_tokens = output[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(answer_tokens, skip_special_tokens=True).strip()


CSS = """
body, .gradio-container { background: #f4f7f5 !important; }
.gradio-container { max-width: 1180px !important; margin: 0 auto !important; color: #18352b !important; }
footer { display: none !important; }
#topbar { align-items: center; padding: 14px 4px 18px; border-bottom: 1px solid #e3ebe6; margin-bottom: 28px; }
#brand-mark { display: flex; align-items: center; gap: 12px; }
.brand-icon { width: 44px; height: 44px; display: grid; place-items: center; border-radius: 15px; background: #dff3e8; font-size: 23px; }
.brand-name { font-size: 17px; font-weight: 750; color: #174d3a; letter-spacing: -.3px; }
.brand-caption { color: #72847b; font-size: 12px; margin-top: 2px; }
.top-badge { display: inline-flex; align-items: center; gap: 8px; border: 1px solid #dce9e1; background: white; color: #426253; border-radius: 999px; padding: 9px 14px; font-size: 12px; font-weight: 650; }
.status-dot { width: 8px; height: 8px; background: #37a66f; border-radius: 50%; }
#hero { padding: 28px 14px 18px 4px; }
.eyebrow { display: inline-block; color: #28744f; background: #e4f4e9; border-radius: 999px; padding: 7px 12px; font-size: 12px; font-weight: 700; letter-spacing: .5px; }
.hero-title { color: #183a2c; font-size: clamp(34px, 4vw, 49px); line-height: 1.08; letter-spacing: -1.8px; font-weight: 780; margin: 20px 0 14px; }
.hero-title span { color: #319166; }
.hero-copy { max-width: 460px; color: #65776e; font-size: 16px; line-height: 1.7; }
#stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 26px 0 24px; }
.stat-card { border: 1px solid #e1eae4; background: #fff; border-radius: 16px; padding: 15px; min-height: 82px; }
.stat-value { color: #1c6548; font-size: 19px; font-weight: 750; }
.stat-label { color: #7a8a82; font-size: 11px; margin-top: 5px; }
#chat-card { background: #fff !important; border: 1px solid #e1eae4 !important; border-radius: 23px !important; box-shadow: 0 14px 40px rgba(22, 61, 43, .07) !important; padding: 22px !important; }
#chat-heading { padding: 0 4px 12px; border-bottom: 1px solid #edf1ee; margin-bottom: 12px; }
#chat-heading h3 { color: #204434; margin-bottom: 4px; }
#chat-heading p { color: #7a8a82; font-size: 13px; margin-top: 0; }
#chat-log { border: 0 !important; background: #fff !important; }
#chat-log .message.user { background: #e5f5ec !important; border: 1px solid #d6eddf !important; color: #204434 !important; }
#chat-log .message.bot { background: #f5f8f6 !important; border: 1px solid #edf1ee !important; color: #263b31 !important; }
#message-row { align-items: center; gap: 8px; }
#message-box textarea { border-radius: 14px !important; border-color: #dce7df !important; background: #fbfdfb !important; }
#send-button { min-width: 96px; border-radius: 13px !important; background: #267a52 !important; }
#send-button:hover { background: #1d6845 !important; }
#clear-button { border-radius: 13px !important; }
#examples-title { color: #718178; font-size: 12px; font-weight: 650; margin: 12px 0 5px; }
.example-row button { border-radius: 12px !important; border-color: #e0e9e3 !important; background: #fbfdfb !important; color: #426253 !important; }
@media (max-width: 700px) {
  #topbar { padding-bottom: 12px; }
  #hero { padding-left: 2px; }
  .hero-title { font-size: 36px; }
  #stats { gap: 6px; }
  .stat-card { padding: 11px 8px; }
  .stat-label { font-size: 10px; }
  #chat-card { padding: 14px !important; }
}
"""

WELCOME = "Halo! Aku asisten informasi laundry. Tanyakan layanan, estimasi, atau cara perawatan pakaian. Kalau data belum tersedia, aku arahkan kamu ke admin."


def submit_message(message, history):
    clean_message = (message or "").strip()
    if not clean_message:
        return history or [], ""
    answer_text = respond(clean_message, history or [])
    updated_history = list(history or [])
    updated_history.extend([
        {"role": "user", "content": clean_message},
        {"role": "assistant", "content": answer_text},
    ])
    return updated_history, ""


with gr.Blocks(
    title="Asisten Laundry",
    theme=gr.themes.Soft(primary_hue="green", secondary_hue="teal", neutral_hue="slate"),
    css=CSS,
) as demo:
    with gr.Row(elem_id="topbar"):
        gr.HTML(
            "<div id='brand-mark'><div class='brand-icon'>🫧</div>"
            "<div><div class='brand-name'>Laundri</div>"
            "<div class='brand-caption'>Asisten informasi laundry</div></div></div>"
        )
        gr.HTML("<div class='top-badge'><span class='status-dot'></span> SIAP MEMBANTU</div>")

    with gr.Row(equal_height=False):
        with gr.Column(scale=5, min_width=300):
            gr.HTML(
                "<section id='hero'><div class='eyebrow'>ASISTEN LAUNDRY BERBASIS AI</div>"
                "<h1 class='hero-title'>Urus laundry,<br><span>lebih mudah.</span></h1>"
                "<p class='hero-copy'>Tanya soal layanan, harga, atau perawatan pakaian. "
                "Jawaban diambil dari informasi laundry yang tersedia.</p></section>"
            )
            model_label = "LoRA aktif" if ADAPTER_DIR and Path(ADAPTER_DIR).exists() else "Qwen dasar"
            gr.HTML(
                "<div id='stats'>"
                f"<div class='stat-card'><div class='stat-value'>{len(FAQS)}</div><div class='stat-label'>FAQ tersedia</div></div>"
                f"<div class='stat-card'><div class='stat-value'>{len(SERVICES)}</div><div class='stat-label'>Layanan terdaftar</div></div>"
                f"<div class='stat-card'><div class='stat-value'>{model_label}</div><div class='stat-label'>Model bahasa</div></div>"
                "</div>"
            )
            gr.Markdown(
                "**Catatan:** untuk harga atau status pesanan yang belum tercantum, "
                "silakan konfirmasi kepada admin."
            )

        with gr.Column(scale=7, min_width=360, elem_id="chat-card"):
            gr.HTML(
                "<div id='chat-heading'><h3>Obrolan</h3>"
                "<p>Asisten akan membantu menjawab pertanyaanmu.</p></div>"
            )
            chat_log = gr.Chatbot(
                value=[{"role": "assistant", "content": WELCOME}],
                type="messages",
                height=430,
                show_label=False,
                bubble_full_width=False,
                elem_id="chat-log",
            )
            with gr.Row(elem_id="message-row"):
                message_box = gr.Textbox(
                    placeholder="Tulis pertanyaan tentang laundry...",
                    show_label=False,
                    lines=1,
                    max_lines=4,
                    container=False,
                    elem_id="message-box",
                )
                send_button = gr.Button("Kirim", variant="primary", elem_id="send-button")
            with gr.Row():
                clear_button = gr.Button("Hapus obrolan", size="sm", elem_id="clear-button")
            gr.Markdown("Contoh pertanyaan", elem_id="examples-title")
            gr.Examples(
                examples=[
                    ["Apa saja layanan laundry?"],
                    ["Berapa harga cuci kiloan?"],
                    ["Bagaimana cara mengambil pesanan?"],
                ],
                inputs=message_box,
                examples_per_page=3,
                elem_classes=["example-row"],
            )

    message_box.submit(submit_message, [message_box, chat_log], [chat_log, message_box])
    send_button.click(submit_message, [message_box, chat_log], [chat_log, message_box])
    clear_button.click(lambda: ([{"role": "assistant", "content": WELCOME}], ""), outputs=[chat_log, message_box])

if __name__ == "__main__":
    demo.launch()

