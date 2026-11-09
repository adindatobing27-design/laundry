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
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype="auto", device_map="auto")
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


demo = gr.ChatInterface(
    fn=respond,
    title="Asisten Laundry",
    description="Tanyakan informasi laundry. Jawaban menggunakan FAQ dan daftar layanan.",
    examples=["Apa saja layanan laundry?", "Berapa harga cuci kiloan?", "Bagaimana cara mengambil pesanan?"],
)

if __name__ == "__main__":
    demo.launch()

