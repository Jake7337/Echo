import os
import json
import torch
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True"

from unsloth import FastLanguageModel
from torch.utils.data import Dataset as TorchDataset
from transformers import Trainer, TrainingArguments, DataCollatorForSeq2Seq

DATASET_PATH = "/kaggle/input/datasets/jakeswander/echo-llm/echo_dataset.json"
MODEL_NAME = "unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit"
MAX_SEQ_LEN = 2048
LORA_RANK = 16
BATCH_SIZE = 2
GRAD_ACCUM = 4
EPOCHS = 5
LR = 2e-4

ALPACA = "Below is an instruction that describes who you are, paired with an input that provides context. Write a response that completes the request.\n\n### Instruction:\n{instruction}\n\n### Input:\n{input}\n\n### Response:\n{output}"
ALPACA_NO_INPUT = "Below is an instruction that describes who you are. Write a response that completes the request.\n\n### Instruction:\n{instruction}\n\n### Response:\n{output}"

print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=MAX_SEQ_LEN,
    dtype=None,
    load_in_4bit=True,
    offload_buffers=True,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=LORA_RANK,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_alpha=16,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)

with open(DATASET_PATH, "r", encoding="utf-8") as f:
    raw = json.load(f)
print(f"Examples: {len(raw)}")

tokenizer.pad_token = tokenizer.eos_token

class EchoDataset(TorchDataset):
    def __init__(self, data, tokenizer, max_len):
        self.data = data
        self.tokenizer = tokenizer
        self.max_len = max_len

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        ex = self.data[idx]
        if ex["input"].strip():
            text = ALPACA.format(instruction=ex["instruction"], input=ex["input"], output=ex["output"])
        else:
            text = ALPACA_NO_INPUT.format(instruction=ex["instruction"], output=ex["output"])
        text += self.tokenizer.eos_token
        enc = self.tokenizer(
            text,
            max_length=self.max_len,
            truncation=True,
            padding=False,
            return_tensors=None,
        )
        enc["labels"] = enc["input_ids"].copy()
        return enc

dataset = EchoDataset(raw, tokenizer, MAX_SEQ_LEN)
collator = DataCollatorForSeq2Seq(tokenizer, model=model, padding=True, pad_to_multiple_of=8)

trainer = Trainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    data_collator=collator,
    args=TrainingArguments(
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        warmup_steps=10,
        num_train_epochs=EPOCHS,
        learning_rate=LR,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=10,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="cosine",
        output_dir="/kaggle/working/echo_lora",
        save_strategy="epoch",
        report_to="none",
    ),
)

print("Training started...")
trainer.train()
print("Training complete.")

print("Saving GGUF...")
model.save_pretrained_gguf("/kaggle/working/echo_gguf", tokenizer, quantization_method="q4_k_m")

import glob
candidates = glob.glob("/kaggle/working/**/*.gguf", recursive=True)
print(f"GGUF saved: {candidates}")
