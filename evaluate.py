"""Membuat perbandingan jawaban Qwen dasar dan Qwen dengan adapter LoRA."""

import csv
import json
import os
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).parent
MODEL_ID = os.getenv("MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct")
ADAPTER_DIR = Path(os.getenv("ADAPTER_DIR", str(ROOT / "adapter-laundry")))
EVAL_FILE = ROOT / "data" / "evaluation_questions.jsonl"
OUTPUT_FILE = ROOT / "hasil_evaluasi.csv"

SYSTEM_MESSAGE = (
    "Kamu adalah asisten informasi laundry yang ramah. Jawab singkat dalam bahasa Indonesia. "
    "Gunakan informasi yang diberikan dan jangan mengarang harga, jam buka, atau status pesanan. "
    "Jika tidak tahu, sarankan pelanggan menghubungi admin."
)


def load_questions():
    with EVAL_FILE.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def load_model(tokenizer, use_adapter):
    has_gpu = torch.cuda.is_available()
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        dtype=torch.float16 if has_gpu else torch.float32,
        device_map="auto",
    )
    if use_adapter:
        if not ADAPTER_DIR.exists():
            raise FileNotFoundError(
                f"Adapter tidak ditemukan di {ADAPTER_DIR}. Jalankan train_lora.py terlebih dahulu."
            )
        model = PeftModel.from_pretrained(model, str(ADAPTER_DIR))
    model.eval()
    return model


def answer(model, tokenizer, question):
    prompt = [
        {"role": "system", "content": SYSTEM_MESSAGE},
        {"role": "user", "content": question},
    ]
    inputs = tokenizer.apply_chat_template(
        prompt,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    ).to(model.device)
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=120,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    new_tokens = output[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def run_for_model(questions, tokenizer, use_adapter):
    model = load_model(tokenizer, use_adapter)
    column = "jawaban_lora" if use_adapter else "jawaban_model_dasar"
    results = [answer(model, tokenizer, item["question"]) for item in questions]
    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return column, results


def main():
    questions = load_questions()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    baseline_column, baseline_answers = run_for_model(questions, tokenizer, use_adapter=False)
    adapted_column, adapted_answers = run_for_model(questions, tokenizer, use_adapter=True)

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["pertanyaan", "jawaban_acuan", baseline_column, adapted_column, "penilaian_manual"],
        )
        writer.writeheader()
        for item, baseline, adapted in zip(questions, baseline_answers, adapted_answers):
            writer.writerow({
                "pertanyaan": item["question"],
                "jawaban_acuan": item["expected_answer"],
                baseline_column: baseline,
                adapted_column: adapted,
                "penilaian_manual": "",
            })
    print(f"Hasil perbandingan tersimpan di: {OUTPUT_FILE}")
    print("Isi kolom penilaian_manual setelah membandingkan ketepatan kedua jawaban.")


if __name__ == "__main__":
    main()

