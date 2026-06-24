"""LoRA fine-tuning adapter for chat-style instruction data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LoraTrainingConfig:
    base_model: str
    train_jsonl: str
    output_dir: str
    validation_jsonl: str | None = None
    max_seq_length: int = 2048
    per_device_train_batch_size: int = 1
    gradient_accumulation_steps: int = 8
    learning_rate: float = 2e-4
    num_train_epochs: float = 3.0
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05


def train_lora(config: LoraTrainingConfig) -> None:
    """Fine-tune a causal LLM with LoRA using TRL SFTTrainer."""

    try:
        from datasets import load_dataset
        from peft import LoraConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from trl import SFTConfig, SFTTrainer
    except ImportError as exc:
        raise ImportError(
            "LoRA training requires optional training dependencies. "
            "Install with: python -m pip install -e .[train]"
        ) from exc

    data_files = {"train": config.train_jsonl}
    if config.validation_jsonl:
        data_files["validation"] = config.validation_jsonl

    dataset = load_dataset("json", data_files=data_files)
    tokenizer = AutoTokenizer.from_pretrained(config.base_model, use_fast=True, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def format_record(record: dict[str, object]) -> str:
        if "messages" in record:
            messages = record["messages"]
            if hasattr(tokenizer, "apply_chat_template"):
                return tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=False,
                )
            return "\n".join(f"{message['role']}: {message['content']}" for message in messages)
        if {"instruction", "input", "output"} <= set(record):
            return (
                f"Instruction: {record['instruction']}\n\n"
                f"Input:\n{record['input']}\n\n"
                f"Output:\n{record['output']}"
            )
        raise ValueError("Training records must contain messages or instruction/input/output")

    model = AutoModelForCausalLM.from_pretrained(
        config.base_model,
        device_map="auto",
        trust_remote_code=True,
    )
    peft_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules="all-linear",
    )
    training_args = SFTConfig(
        output_dir=config.output_dir,
        per_device_train_batch_size=config.per_device_train_batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        num_train_epochs=config.num_train_epochs,
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="epoch" if config.validation_jsonl else "no",
        report_to="none",
        max_length=config.max_seq_length,
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset.get("validation"),
        peft_config=peft_config,
        processing_class=tokenizer,
        formatting_func=format_record,
    )
    trainer.train()
    Path(config.output_dir).mkdir(parents=True, exist_ok=True)
    trainer.save_model(config.output_dir)
    tokenizer.save_pretrained(config.output_dir)
