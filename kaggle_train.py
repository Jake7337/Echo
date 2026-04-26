import os
import json
import torch
import glob
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True"

from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer

DATASET_PATH = "/kaggle/input/datasets/jakeswander/echo-llm/echo_dataset.json"
MODEL_NAME = "unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit"
MAX_SEQ_LEN = 2048
LORA_RANK = 16
BATCH_SIZE = 2
GRAD_ACCUM = 4
EPOCHS = 5
LR = 2e-4

ALPACA = """Below is an instruction that describes who you are, paired with an input that provides context. Write a response that completes the request.

### Instruction:
{instruction}

### Input:
{input}

### Response:
{output}"""

ALPACA_NO_INPUT = """Below is an instruction that describes who you are. Write a response that completes the request.

### Instruction:
{instruction}

### Response:
{output}"""

print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=dtype,
)

print("Loading model...")
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=dtype,
)
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
tokenizer.pad_token = tokenizer.eos_token

lora_config = LoraConfig(
    r=LORA_RANK,
    lora_alpha=16,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0.0,
    bias="none",
    task_type=TaskType.CAUSAL_LM,
)
model = get_peft_model(model, lora_config)
model.enable_input_require_grads()
model.print_trainable_parameters()

with open(DATASET_PATH, "r", encoding="utf-8") as f:
    raw = json.load(f)
print(f"Examples: {len(raw)}")

texts = []
for ex in raw:
    if ex["input"].strip():
        text = ALPACA.format(instruction=ex["instruction"], input=ex["input"], output=ex["output"])
    else:
        text = ALPACA_NO_INPUT.format(instruction=ex["instruction"], output=ex["output"])
    texts.append({"text": text + tokenizer.eos_token})

dataset = Dataset.from_list(texts)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LEN,
    packing=False,
    args=TrainingArguments(
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        warmup_steps=10,
        num_train_epochs=EPOCHS,
        learning_rate=LR,
        fp16=(dtype == torch.float16),
        bf16=(dtype == torch.bfloat16),
        logging_steps=10,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="cosine",
        output_dir="/kaggle/working/echo_lora",
        save_strategy="epoch",
        report_to="none",
        gradient_checkpointing=True,
    ),
)

print("Training started...")
trainer.train()
print("Training complete.")

print("Merging and saving model...")
merged = trainer.model.merge_and_unload()
merged.save_pretrained("/kaggle/working/echo_merged")
tokenizer.save_pretrained("/kaggle/working/echo_merged")
print("Merged model saved.")

print("Converting to GGUF...")
os.system("git clone https://github.com/ggerganov/llama.cpp /kaggle/working/llama.cpp --depth 1 -q")
os.system("pip install -r /kaggle/working/llama.cpp/requirements.txt -q")
os.system("python /kaggle/working/llama.cpp/convert_hf_to_gguf.py /kaggle/working/echo_merged --outtype q4_k_m --outfile /kaggle/working/echo-finetuned.gguf")

candidates = glob.glob("/kaggle/working/*.gguf")
print(f"GGUF saved: {candidates}")
