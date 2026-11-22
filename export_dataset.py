#!/usr/bin/env python3
"""Export, inspect, and evaluate Green Man's approved_actions.jsonl dataset.

Supports:
  - stats:  Summarize recorded examples by source, tool, model, and image health.
  - export: Convert approved_actions.jsonl to OpenAI/Unsloth or ShareGPT/LLaMA-Factory
            multimodal tool-calling format, with optional filtering and train/val split.
  - eval:   Replay recorded (screenshot, prompt) pairs against a local Ollama model
            and score tool-call accuracy against your approved actions.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    from dataset_recorder import default_dataset_directory
except ImportError:
    def default_dataset_directory() -> Path:
        data_home = Path(
            os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        ).expanduser()
        return data_home / "local-green-man-assistant" / "dataset"


DEFAULT_SYSTEM_PROMPTS = {
    "pong_study": (
        "You are playing Pong using the right paddle. Compare the vertical centres "
        "of the ball and right paddle, then choose exactly one tool call: press_key "
        "(i up, k down) or wait."
    ),
    "chess_study": (
        "You are playing chess in the Green Man Chess window. The board has a-h "
        "columns and 1-8 rows. Choose exactly one tool call: move_piece with "
        "from_square and to_square, or wait."
    ),
    "default": (
        "You are Green Man, a local desktop assistant. Inspect the screenshot and "
        "user request, then choose the appropriate tool call."
    ),
}

PONG_EVAL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Move the right paddle: i up or k down.",
            "parameters": {
                "type": "object",
                "properties": {
                    "observation": {"type": "string"},
                    "ball_visible": {"type": "boolean"},
                    "paddle_visible": {"type": "boolean"},
                    "keys": {"type": "string", "enum": ["i", "k"]},
                    "duration_seconds": {"type": "number", "minimum": 0.02, "maximum": 0.5},
                },
                "required": ["observation", "ball_visible", "paddle_visible", "keys", "duration_seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Do not move the paddle for a short interval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "observation": {"type": "string"},
                    "seconds": {"type": "number", "minimum": 0.1, "maximum": 1},
                },
                "required": ["observation", "seconds"],
            },
        },
    },
]

CHESS_EVAL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "move_piece",
            "description": "Move a chess piece from from_square to to_square (a1-h8).",
            "parameters": {
                "type": "object",
                "properties": {
                    "observation": {"type": "string"},
                    "from_square": {"type": "string"},
                    "to_square": {"type": "string"},
                },
                "required": ["observation", "from_square", "to_square"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait briefly when it is not your turn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "observation": {"type": "string"},
                    "seconds": {"type": "number", "minimum": 0.1, "maximum": 1},
                },
                "required": ["observation", "seconds"],
            },
        },
    },
]


def load_entries(jsonl_path: Path) -> list[dict[str, Any]]:
    if not jsonl_path.is_file():
        raise FileNotFoundError(f"Dataset file not found: {jsonl_path}")
    entries: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(
        jsonl_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_no} of {jsonl_path}: {exc}") from exc
        if isinstance(item, dict):
            entries.append(item)
    return entries


def resolve_image_path(dataset_dir: Path, entry: dict[str, Any]) -> Path | None:
    rel = entry.get("screenshot")
    if not rel or not isinstance(rel, str):
        return None
    candidate = (dataset_dir / rel).resolve()
    return candidate if candidate.is_file() else None


def encode_image_data_uri(image_path: Path) -> str:
    raw = image_path.read_bytes()
    mime = "image/png" if raw.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def filter_entries(
    entries: list[dict[str, Any]],
    dataset_dir: Path,
    *,
    sources: list[str] | None = None,
    tools: list[str] | None = None,
    require_image: bool = False,
    deduplicate: bool = False,
) -> list[dict[str, Any]]:
    source_set = {s.casefold() for s in sources} if sources else None
    tool_set = {t.casefold() for t in tools} if tools else None
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []

    for entry in entries:
        source = str(entry.get("source", ""))
        tool_call = entry.get("tool_call") or {}
        tool_name = str(tool_call.get("name", ""))
        if source_set and source.casefold() not in source_set:
            continue
        if tool_set and tool_name.casefold() not in tool_set:
            continue
        if require_image and resolve_image_path(dataset_dir, entry) is None:
            continue
        if deduplicate:
            key = json.dumps(
                {
                    "source": source,
                    "prompt": entry.get("prompt", ""),
                    "screenshot": entry.get("screenshot"),
                    "tool_call": tool_call,
                },
                sort_keys=True,
                ensure_ascii=False,
            )
            if key in seen:
                continue
            seen.add(key)
        kept.append(entry)
    return kept


def system_prompt_for_entry(entry: dict[str, Any]) -> str:
    if isinstance(entry.get("system_prompt"), str) and entry["system_prompt"].strip():
        return entry["system_prompt"].strip()
    source = str(entry.get("source", ""))
    return DEFAULT_SYSTEM_PROMPTS.get(source, DEFAULT_SYSTEM_PROMPTS["default"])


def to_openai_example(
    entry: dict[str, Any],
    dataset_dir: Path,
    *,
    embed_images: bool = False,
) -> dict[str, Any]:
    prompt_text = str(entry.get("prompt", "")).strip() or "Perform the next action."
    image_path = resolve_image_path(dataset_dir, entry)
    tool_call = entry.get("tool_call") or {}
    tool_name = str(tool_call.get("name", ""))
    tool_args = tool_call.get("arguments") or {}

    if image_path is not None:
        image_ref = encode_image_data_uri(image_path) if embed_images else str(image_path)
        user_content: Any = [
            {"type": "image_url", "image_url": {"url": image_ref}},
            {"type": "text", "text": prompt_text},
        ]
    else:
        user_content = prompt_text

    return {
        "messages": [
            {"role": "system", "content": system_prompt_for_entry(entry)},
            {"role": "user", "content": user_content},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(tool_args, ensure_ascii=False),
                        },
                    }
                ],
            },
        ],
        "metadata": {
            "timestamp": entry.get("timestamp"),
            "source": entry.get("source"),
            "model": entry.get("model"),
            "screenshot_size": entry.get("screenshot_size"),
        },
    }


def to_sharegpt_example(entry: dict[str, Any], dataset_dir: Path) -> dict[str, Any]:
    prompt_text = str(entry.get("prompt", "")).strip() or "Perform the next action."
    image_path = resolve_image_path(dataset_dir, entry)
    tool_call = entry.get("tool_call") or {}
    assistant_payload = json.dumps(
        {
            "name": tool_call.get("name", ""),
            "arguments": tool_call.get("arguments") or {},
        },
        ensure_ascii=False,
    )

    user_value = f"<image>\n{prompt_text}" if image_path is not None else prompt_text
    example: dict[str, Any] = {
        "conversations": [
            {"from": "system", "value": system_prompt_for_entry(entry)},
            {"from": "human", "value": user_value},
            {"from": "function_call", "value": assistant_payload},
        ]
    }
    if image_path is not None:
        example["images"] = [str(image_path)]
    return example


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def cmd_stats(args: argparse.Namespace) -> int:
    jsonl_path = Path(args.input).expanduser().resolve()
    dataset_dir = jsonl_path.parent
    entries = load_entries(jsonl_path)

    sources = Counter(str(e.get("source", "unknown")) for e in entries)
    tools = Counter(str((e.get("tool_call") or {}).get("name", "unknown")) for e in entries)
    models = Counter(str(e.get("model", "unknown")) for e in entries)

    with_image = 0
    missing_image = 0
    without_image = 0
    for entry in entries:
        if not entry.get("screenshot"):
            without_image += 1
        elif resolve_image_path(dataset_dir, entry) is not None:
            with_image += 1
        else:
            missing_image += 1

    print(f"Dataset file : {jsonl_path}")
    print(f"Total entries: {len(entries)}")
    print(f"Images       : {with_image} valid, {without_image} text-only, {missing_image} missing on disk")
    if sources:
        print("\nBy source:")
        for name, count in sources.most_common():
            print(f"  {name}: {count}")
    if tools:
        print("\nBy tool:")
        for name, count in tools.most_common():
            print(f"  {name}: {count}")
    if models:
        print("\nBy model:")
        for name, count in models.most_common():
            print(f"  {name}: {count}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    jsonl_path = Path(args.input).expanduser().resolve()
    dataset_dir = jsonl_path.parent
    entries = load_entries(jsonl_path)
    filtered = filter_entries(
        entries,
        dataset_dir,
        sources=args.source,
        tools=args.tool,
        require_image=args.require_image,
        deduplicate=args.deduplicate,
    )

    if not filtered:
        print("No matching entries found to export.", file=sys.stderr)
        return 1

    if args.format == "openai":
        converted = [
            to_openai_example(e, dataset_dir, embed_images=args.embed_images)
            for e in filtered
        ]
    elif args.format == "sharegpt":
        converted = [to_sharegpt_example(e, dataset_dir) for e in filtered]
    else:
        raise ValueError(f"Unsupported format: {args.format}")

    output_path = Path(args.output).expanduser().resolve()
    if args.val_split > 0:
        if not 0 < args.val_split < 1:
            raise ValueError("--val-split must be between 0 and 1.")
        rng = random.Random(args.seed)
        shuffled = list(converted)
        rng.shuffle(shuffled)
        val_count = max(1, round(len(shuffled) * args.val_split))
        val_records = shuffled[:val_count]
        train_records = shuffled[val_count:]
        stem = output_path.stem
        suffix = output_path.suffix or ".jsonl"
        train_path = output_path.with_name(f"{stem}_train{suffix}")
        val_path = output_path.with_name(f"{stem}_val{suffix}")
        write_jsonl(train_path, train_records)
        write_jsonl(val_path, val_records)
        print(f"Exported {len(train_records)} train -> {train_path}")
        print(f"Exported {len(val_records)} val   -> {val_path}")
    else:
        write_jsonl(output_path, converted)
        print(f"Exported {len(converted)} examples ({args.format}) -> {output_path}")
    return 0


def _local_ollama_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Ollama URL must use http://localhost, 127.0.0.1, or ::1.")
    return url.rstrip("/")


def _tools_for_eval(source: str) -> list[dict[str, Any]]:
    if source == "pong_study":
        return PONG_EVAL_TOOLS
    if source == "chess_study":
        return CHESS_EVAL_TOOLS
    try:
        from app import tools_for_mode
        return tools_for_mode(source)
    except Exception:
        return []


def _compare_tool_calls(
    expected_name: str,
    expected_args: dict[str, Any],
    predicted_name: str | None,
    predicted_args: dict[str, Any] | None,
) -> tuple[bool, bool]:
    name_match = predicted_name == expected_name
    if not name_match or not isinstance(predicted_args, dict):
        return name_match, False
    # Ignore free-text observation strings when checking action equivalence
    exp_clean = {k: v for k, v in expected_args.items() if k != "observation"}
    pred_clean = {k: v for k, v in predicted_args.items() if k != "observation"}
    return True, exp_clean == pred_clean


def cmd_eval(args: argparse.Namespace) -> int:
    jsonl_path = Path(args.input).expanduser().resolve()
    dataset_dir = jsonl_path.parent
    api_url = _local_ollama_url(args.ollama_url) + "/api/chat"
    entries = load_entries(jsonl_path)
    filtered = filter_entries(
        entries,
        dataset_dir,
        sources=args.source,
        tools=args.tool,
        require_image=args.require_image,
    )
    if args.limit and args.limit > 0:
        filtered = filtered[: args.limit]
    if not filtered:
        print("No matching entries found to evaluate.", file=sys.stderr)
        return 1

    name_matches = 0
    exact_matches = 0
    total_eval_tokens = 0
    total_eval_ns = 0
    results: list[dict[str, Any]] = []

    for idx, entry in enumerate(filtered, start=1):
        source = str(entry.get("source", ""))
        expected_call = entry.get("tool_call") or {}
        expected_name = str(expected_call.get("name", ""))
        expected_args = expected_call.get("arguments") or {}

        user_msg: dict[str, Any] = {
            "role": "user",
            "content": str(entry.get("prompt", "")).strip() or "Perform the next action.",
        }
        image_path = resolve_image_path(dataset_dir, entry)
        if image_path is not None:
            user_msg["images"] = [base64.b64encode(image_path.read_bytes()).decode("ascii")]

        payload: dict[str, Any] = {
            "model": args.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt_for_entry(entry)},
                user_msg,
            ],
            "options": {"temperature": 0.0},
        }
        tools = _tools_for_eval(source)
        if tools:
            payload["tools"] = tools

        req = Request(
            api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        t0 = time.monotonic()
        try:
            with urlopen(req, timeout=args.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"[{idx}/{len(filtered)}] ERROR: {exc}", file=sys.stderr)
            results.append({"index": idx, "error": str(exc), "expected": expected_call})
            continue
        elapsed = time.monotonic() - t0

        total_eval_tokens += int(data.get("eval_count", 0))
        total_eval_ns += int(data.get("eval_duration", 0))

        message = data.get("message") or {}
        calls = message.get("tool_calls") or []
        pred_name = None
        pred_args = None
        if calls and isinstance(calls[0], dict):
            fn = calls[0].get("function") or {}
            pred_name = fn.get("name")
            pred_args = fn.get("arguments")

        name_ok, exact_ok = _compare_tool_calls(expected_name, expected_args, pred_name, pred_args)
        name_matches += int(name_ok)
        exact_matches += int(exact_ok)

        status = "EXACT" if exact_ok else ("TOOL_OK" if name_ok else "MISS")
        print(
            f"[{idx}/{len(filtered)}] {status:<7} ({elapsed:.1f}s) "
            f"expected={expected_name} predicted={pred_name}"
        )
        results.append(
            {
                "index": idx,
                "source": source,
                "status": status,
                "elapsed_seconds": round(elapsed, 3),
                "expected": expected_call,
                "predicted": {"name": pred_name, "arguments": pred_args},
            }
        )

    total = len(filtered)
    avg_tps = (
        total_eval_tokens / (total_eval_ns / 1_000_000_000.0)
        if total_eval_tokens > 0 and total_eval_ns > 0
        else 0.0
    )
    print("\n--- Evaluation Summary ---")
    print(f"Model         : {args.model}")
    print(f"Examples      : {total}")
    print(f"Tool match    : {name_matches}/{total} ({name_matches / total * 100:.1f}%)")
    print(f"Exact match   : {exact_matches}/{total} ({exact_matches / total * 100:.1f}%)")
    if avg_tps > 0:
        print(f"Avg throughput: {avg_tps:.1f} tok/s")

    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "model": args.model,
                    "total": total,
                    "tool_match_count": name_matches,
                    "exact_match_count": exact_matches,
                    "avg_tokens_per_second": round(avg_tps, 2),
                    "results": results,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Saved report  : {report_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    default_input = str(default_dataset_directory() / "approved_actions.jsonl")
    parser = argparse.ArgumentParser(
        description="Inspect, export, and evaluate Green Man's approved-actions dataset."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_stats = sub.add_parser("stats", help="Show summary statistics for the dataset.")
    p_stats.add_argument("-i", "--input", default=default_input, help="Path to approved_actions.jsonl")
    p_stats.set_defaults(func=cmd_stats)

    p_export = sub.add_parser("export", help="Convert dataset to fine-tuning JSONL format.")
    p_export.add_argument("-i", "--input", default=default_input, help="Path to approved_actions.jsonl")
    p_export.add_argument("-o", "--output", default="greenman_finetune.jsonl", help="Output JSONL path")
    p_export.add_argument(
        "-f", "--format", choices=("openai", "sharegpt"), default="openai",
        help="Target format: openai (Unsloth/Axolotl/Qwen-VL) or sharegpt (LLaMA-Factory).",
    )
    p_export.add_argument("--source", action="append", help="Filter by source (repeatable, e.g. --source chess_study)")
    p_export.add_argument("--tool", action="append", help="Filter by tool name (repeatable)")
    p_export.add_argument("--require-image", action="store_true", help="Skip entries without a valid image file")
    p_export.add_argument("--deduplicate", action="store_true", help="Drop exact duplicate entries")
    p_export.add_argument("--embed-images", action="store_true", help="Embed images as base64 data URIs (openai format)")
    p_export.add_argument("--val-split", type=float, default=0.0, help="Fraction for validation split (e.g. 0.1)")
    p_export.add_argument("--seed", type=int, default=42, help="Random seed for validation split")
    p_export.set_defaults(func=cmd_export)

    p_eval = sub.add_parser("eval", help="Benchmark a local Ollama model against recorded actions.")
    p_eval.add_argument("-i", "--input", default=default_input, help="Path to approved_actions.jsonl")
    p_eval.add_argument("-m", "--model", required=True, help="Ollama model name (e.g. qwen3-vl:8b-instruct)")
    p_eval.add_argument("--ollama-url", default="http://127.0.0.1:11434", help="Local Ollama base URL")
    p_eval.add_argument("--source", action="append", help="Filter by source (repeatable)")
    p_eval.add_argument("--tool", action="append", help="Filter by tool name (repeatable)")
    p_eval.add_argument("--require-image", action="store_true", help="Only evaluate entries with screenshots")
    p_eval.add_argument("--limit", type=int, default=0, help="Evaluate at most N entries")
    p_eval.add_argument("--timeout", type=int, default=180, help="Per-request timeout in seconds")
    p_eval.add_argument("--report", help="Optional path to save a JSON evaluation report")
    p_eval.set_defaults(func=cmd_eval)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
