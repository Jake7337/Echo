"""
build_dataset.py
Converts Echo's approved training examples into Unsloth Alpaca JSON format.
Run once to generate echo_dataset.json for LoRA fine-tuning.

Usage:
    python build_dataset.py
Output:
    echo_dataset.json
"""

import json
import re
import os

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
IDENTITY_FILE = os.path.join(SCRIPT_DIR, "identity.md")
SOURCE_FILES = [
    r"C:\Users\jrsrl\Desktop\claude code share _show\VOICE RESPONSES — batch 1 of 10.txt",
    r"C:\Users\jrsrl\Desktop\claude code share _show\batch8.txt",
    r"C:\Users\jrsrl\Desktop\claude code share _show\from_discord_convo.txt",
    r"C:\Users\jrsrl\Desktop\claude code share _show\examples\1 to 200.txt",
    r"C:\Users\jrsrl\Desktop\claude code share _show\examples\Voice responses (201-400).txt",
    r"C:\Users\jrsrl\Desktop\claude code share _show\examples\Voice responses more.txt",
]
OUTPUT_FILE  = os.path.join(SCRIPT_DIR, "echo_dataset.json")


def load_identity() -> str:
    with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def parse_examples(text: str) -> list:
    """Extract all input/output pairs from the raw approved text.

    Handles four formats:
      1. input: "..." / output: "..."          — original batch format
      2. Jake: "..." / Echo: "..."             — voice session format
      3. User: "..." / Echo: "..."             — user prompt format
      4. Q: "..."   / Echo: "..."             — personality Q&A format
      5. Standalone heartbeat lines            — no input label, Echo's own thought
    """
    INPUT_PREFIXES  = ('jake:', 'user:', 'q:')
    OUTPUT_PREFIX   = 'echo:'
    LEGACY_IN       = 'input:'
    LEGACY_OUT      = 'output:'
    # Lines that look like section headers / file metadata — skip them
    SKIP_PREFIXES   = ('category ', 'voice responses', 'real conversation',
                       'from discord', '#', '---', 'batch', 'heartbeat thoughts',
                       'memory responses', 'personality under pressure',
                       'rejections', 'ready for', "that's ")
    # Substrings that indicate garbage / Claude-session meta-commentary
    SKIP_CONTAINS   = ('you said:', 'claude responded:', 'click to react',
                       'add reaction', 'am claude', ':thumbsup:', ':fire:',
                       ':heart:', 'let me know when', 'personality under pressure',
                       'on to personality', 'round 2', 'full rotation')

    examples = []
    seen     = set()   # deduplication key: (input, output)
    lines    = text.splitlines()

    def is_header(line: str) -> bool:
        low = line.lower()
        for s in SKIP_PREFIXES:
            if low.startswith(s):
                return True
        for s in SKIP_CONTAINS:
            if s in low:
                return True
        # Lines with AM/PM timestamps embedded (like "2:09 AMClaude")
        import re
        if re.search(r'\d:\d\d [AP]M', line):
            return True
        return False

    def add(inp: str, out: str):
        key = (inp.strip(), out.strip())
        if key not in seen and key[1]:
            seen.add(key)
            examples.append({"input": key[0], "output": key[1]})

    def strip_quotes(s: str) -> str:
        return s.strip().strip('"').strip("'")

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        low = line.lower()

        # ── Format 1: legacy input:/output: ──────────────────────────────
        if low.startswith(LEGACY_IN):
            raw_input = strip_quotes(line[len(LEGACY_IN):])
            j = i + 1
            while j < len(lines) and not lines[j].strip().lower().startswith(LEGACY_OUT):
                j += 1
            if j < len(lines):
                raw_output = strip_quotes(lines[j].strip()[len(LEGACY_OUT):])
                add(raw_input, raw_output)
                i = j + 1
                continue

        # ── Formats 2-4: Jake/User/Q → Echo ─────────────────────────────
        elif any(low.startswith(p) for p in INPUT_PREFIXES):
            colon_idx = line.index(':')
            raw_input = strip_quotes(line[colon_idx + 1:])
            # Next non-blank line should be Echo:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].strip().lower().startswith(OUTPUT_PREFIX):
                raw_output = strip_quotes(lines[j].strip()[len(OUTPUT_PREFIX):])
                add(raw_input, raw_output)
                i = j + 1
                continue

        # ── Format 5: standalone heartbeat line ──────────────────────────
        elif (not is_header(line)
              and not low.startswith(OUTPUT_PREFIX)
              and len(line) > 20
              and not line.endswith(':')
              and '/' not in line[:6]):      # skip file-path-like lines
            add("", line)

        i += 1

    return examples


def build_dataset(instruction: str, examples: list) -> list:
    """Wrap examples in Alpaca format with shared instruction."""
    return [
        {
            "instruction": instruction,
            "input":       ex["input"],
            "output":      ex["output"],
        }
        for ex in examples
    ]


def main():
    print("Loading identity...", flush=True)
    instruction = load_identity()

    print(f"Loading source files...", flush=True)
    raw = ""
    for path in SOURCE_FILES:
        with open(path, "r", encoding="utf-8") as f:
            raw += f.read() + "\n"

    print("Parsing examples...", flush=True)
    examples = parse_examples(raw)
    print(f"Found {len(examples)} examples.", flush=True)

    dataset = build_dataset(instruction, examples)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    print(f"Dataset written to {OUTPUT_FILE}", flush=True)
    print(f"Ready for Unsloth fine-tuning.", flush=True)

    # Quick sanity check
    print("\nSample entries:")
    for entry in dataset[:2]:
        print(f"  input:  {entry['input'][:60]!r}")
        print(f"  output: {entry['output'][:60]!r}")
        print()
    print(f"  [heartbeat example]")
    heartbeats = [e for e in dataset if e['input'] == '']
    if heartbeats:
        print(f"  input:  ''")
        print(f"  output: {heartbeats[0]['output'][:60]!r}")


if __name__ == "__main__":
    main()
