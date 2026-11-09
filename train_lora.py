import json
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, DataCollatorForLanguageModeling, Trainer, TrainingArguments

MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
DATA_FILE = Path("data/laundry_faq.jsonl")
OUTPUT_DIR = "adapter-laundry"


def main():
    with DATA_FILE.open(encoding="utf-8") as file:
        source = [json.loads(line) for line in file if line.strip()]

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto",
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
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

    texts = []
    for item in source:
        texts.append({"text": tokenizer.apply_chat_template(
            [
                {"role": "user", "content": item["question"]},
                {"role": "assistant", "content": item["answer"]},
            ],
            tokenize=False,
            add_generation_prompt=False,
        )})
    dataset = Dataset.from_list(texts)

    def tokenize(batch):
        return tokenizer(batch["text"], truncation=True, max_length=256)

    tokenized = dataset.map(tokenize, batched=True, remove_columns=["text"])
    args = TrainingArguments(
        output_dir="hasil-lora-laundry",
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        num_train_epochs=5,
        learning_rate=2e-4,
        logging_steps=1,
        save_strategy="epoch",
        report_to="none",
        fp16=torch.cuda.is_available(),
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=tokenized,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )
    trainer.train()
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"Adapter tersimpan di {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

