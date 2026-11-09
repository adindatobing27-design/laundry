"""Adaptasi ringan Qwen untuk tanya jawab laundry menggunakan LoRA."""

import json
import shutil
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

ROOT = Path(__file__).parent
MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
DATA_FILE = ROOT / "data" / "laundry_faq.jsonl"
OUTPUT_DIR = ROOT / "adapter-laundry"
MAX_LENGTH = 512

SYSTEM_MESSAGE = (
    "Kamu adalah asisten informasi laundry yang ramah. Jawab singkat dalam bahasa Indonesia. "
    "Gunakan informasi yang diberikan dan jangan mengarang harga atau status pesanan."
)


class AssistantOnlyCollator:
    """Membuat loss hanya menghitung token jawaban asisten, bukan pertanyaan."""

    def __init__(self, tokenizer):
        self.tokenizer = tokenizer

    def __call__(self, features):
        input_features = [
            {"input_ids": item["input_ids"], "attention_mask": item["attention_mask"]}
            for item in features
        ]
        batch = self.tokenizer.pad(input_features, padding=True, return_tensors="pt")
        labels = torch.full_like(batch["input_ids"], -100)
        for row, item in enumerate(features):
            item_labels = torch.tensor(item["labels"], dtype=torch.long)
            labels[row, : len(item_labels)] = item_labels
        batch["labels"] = labels
        return batch


def load_examples():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Dataset tidak ditemukan: {DATA_FILE}")
    with DATA_FILE.open(encoding="utf-8") as file:
        rows = [json.loads(line) for line in file if line.strip()]
    if not rows:
        raise ValueError("Dataset masih kosong.")
    for index, row in enumerate(rows, start=1):
        if not row.get("question") or not row.get("answer"):
            raise ValueError(f"Contoh nomor {index} perlu memiliki question dan answer.")
    return rows


def make_features(rows, tokenizer):
    features = []
    for row in rows:
        prompt = [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": row["question"]},
        ]
        complete = prompt + [{"role": "assistant", "content": row["answer"]}]
        prompt_ids = tokenizer.apply_chat_template(
            prompt, tokenize=True, add_generation_prompt=True
        )
        full_ids = tokenizer.apply_chat_template(
            complete, tokenize=True, add_generation_prompt=False
        )

        # Hitung prefix yang sama; beberapa template menambahkan token pembuka jawaban.
        prefix_length = 0
        for prompt_token, full_token in zip(prompt_ids, full_ids):
            if prompt_token != full_token:
                break
            prefix_length += 1

        input_ids = full_ids[:MAX_LENGTH]
        labels = [-100] * min(prefix_length, len(input_ids))
        labels.extend(input_ids[len(labels):])
        if not any(token != -100 for token in labels):
            raise ValueError(f"Jawaban untuk pertanyaan '{row['question']}' terpotong seluruhnya.")

        features.append({"input_ids": input_ids, "attention_mask": [1] * len(input_ids), "labels": labels})
    return Dataset.from_list(features)


def main():
    rows = load_examples()
    has_gpu = torch.cuda.is_available()
    print(f"Model: {MODEL_ID}")
    print(f"Jumlah contoh: {len(rows)}")
    print(f"Perangkat: {'GPU' if has_gpu else 'CPU (proses bisa lama)'}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        dtype=torch.float16 if has_gpu else torch.float32,
        device_map="auto",
    )
    model.config.use_cache = False
    model.config.pad_token_id = tokenizer.pad_token_id
    model = get_peft_model(
        model,
        LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        ),
    )
    model.print_trainable_parameters()

    training_data = make_features(rows, tokenizer)
    args = TrainingArguments(
        output_dir=str(ROOT / "hasil-lora-laundry"),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        num_train_epochs=5,
        learning_rate=2e-4,
        logging_steps=1,
        save_strategy="epoch",
        save_total_limit=1,
        report_to="none",
        fp16=has_gpu,
        remove_unused_columns=False,
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=training_data,
        data_collator=AssistantOnlyCollator(tokenizer),
    )
    trainer.train()

    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    shutil.make_archive(str(ROOT / "adapter-laundry"), "zip", root_dir=OUTPUT_DIR)
    print(f"Adapter LoRA tersimpan di: {OUTPUT_DIR}")
    print(f"File untuk dipindahkan ke laptop: {ROOT / 'adapter-laundry.zip'}")


if __name__ == "__main__":
    main()

