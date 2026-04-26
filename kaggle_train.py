import os
import json
import torch
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True"

from datasets import Dataset
from unsloth import FastLanguageModel
from trl import SFTTrainer
from transformers import TrainingArguments

DATASET_PATH = "/kaggle/input/datasets/jakeswander/echo-llm/echo_dataset.json"
MODEL_NAME = "unsloth/Qwen2.5-3B-Instruct-bnb-4bit"
MAX_SEQ_LEN = 512
LORA_RANK = 8
BATCH_SIZE = 1
GRAD_ACCUM = 8
EPOCHS = 5
LR = 2e-4

ALPACA = (
    "Below is an instruction that describes who you are, paired with an input that provides context. "
    "Write a response that completes the request.\n\n"
    "### Instruction:\n{instruction}\n\n"
    "### Input:\n{input}\n\n"
    "### Response:\n{output}"
)

ALPACA_NO_INPUT = (
    "Below is an instruction that describes who you are. "
    "Write a response that completes the request.\n\n"
    "### Instruction:\n{instruction}\n\n"
    "### Response:\n{output}"
)

print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=MAX_SEQ_LEN,
    dtype=None,
    load_in_4bit=True,
    offload_buffers=True,
)
EOS = tokenizer.eos_token

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

def fmt(examples):
    texts = []
    for instr, inp, out in zip(examples["instruction"], examples["input"], examples["output"]):
        if inp.strip():
            t = ALPACA.format(instruction=instr, input=inp, output=out)
        else:
            t = ALPACA_NO_INPUT.format(instruction=instr, output=out)
        texts.append(t + EOS)
    return {"text": texts}

dataset = Dataset.from_list(raw).map(fmt, batched=True)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LEN,
    dataset_num_proc=2,
    packing=False,
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
