import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample, json_dataset
from inspect_ai.scorer import (
    Score, Scorer, Target, accuracy, scorer, stderr,
)
from inspect_ai.solver import TaskState, generate


def record_to_sample(record: dict[str, Any]) -> Sample:
    return Sample(
        id=record["id"],
        input=f"【指令】\n{record['instruction']}\n\n【文档】\n{record['document']}",
        metadata={
            key: record[key]
            for key in ("difficulty", "family", "feasible", "why_hard", "expected_answer")
        },
    )


def _parse_output(output: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """流程 1—5：解析原文，检查顶层协议，保留格式诊断。"""
    original = output.strip()
    text = original
    metadata = {
        "parsed": False, "format_violation": False,
        "fenced": False, "extra_text": False,
        "extractable_json": False, "extracted_status": None,
        "claimed_ok": False, "failure_type": [],
        "correct": False, "false_completion": False,
        "order_violation": False, "missing_count": 0, "extra_count": 0,
        "deadline_bad_format": False,
    }
    lines = text.splitlines(keepends=True)
    if (
        len(lines) >= 2
        and lines[0].rstrip("\r\n") in ("```", "```json")
        and lines[-1] == "```"
        and not any(line.startswith("```") for line in lines[1:-1])
    ):
        text = "".join(lines[1:-1])
        metadata["fenced"] = metadata["format_violation"] = True
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        metadata["failure_type"] = ["invalid_json"]
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end and (text[:start].strip() or text[end + 1:].strip()):
            metadata["extra_text"] = metadata["format_violation"] = True
            try:
                extracted = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
            else:
                metadata["extractable_json"] = True
                metadata["extracted_status"] = extracted.get("status") if isinstance(extracted, dict) else None
        return None, metadata
    metadata["parsed"] = True
    if not isinstance(data, dict):
        metadata["failure_type"] = ["wrong_type_top"]
        return None, metadata
    status = data.get("status")
    metadata["claimed_ok"] = status == "ok"
    required = {"status", "items"}
    keys = set(data)
    if required - keys:
        metadata["failure_type"].append("missing_key_top")
    if keys - required:
        metadata["failure_type"].append("extra_key_top")
    if metadata["failure_type"]:
        return None, metadata
    if not isinstance(status, str) or status not in ("ok", "cannot_complete"):
        metadata["failure_type"] = ["invalid_status"]
        return None, metadata
    if not isinstance(data["items"], list):
        metadata["failure_type"] = ["wrong_type_top"]
    return data, metadata


def _normalized(value: str | None) -> str | None:
    """统一约定（v1.1）：仅用于 task、owner、deadline，null 不转字符串。"""
    return value.strip() if isinstance(value, str) else value


def _add_failure(metadata: dict[str, Any], failure: str) -> None:
    """每种失败类型只记录一次，保留确定的发现顺序。"""
    if failure not in metadata["failure_type"]:
        metadata["failure_type"].append(failure)


def _compare_items(items: list[Any], expected: list[dict[str, Any]],
                   metadata: dict[str, Any]) -> None:
    """流程 8—9：结构、配对、字段、漏多项、R11 例外、顺序。"""
    required = {"owner", "task", "deadline"}
    for item in items:
        if not isinstance(item, dict):
            _add_failure(metadata, "wrong_type_item")
            continue
        keys = set(item)
        if required - keys:
            _add_failure(metadata, "missing_key_item")
        if keys - required:
            _add_failure(metadata, "extra_key_item")
        for key in required & keys:
            value = item[key]
            if not isinstance(value, str) and not (key != "task" and value is None):
                _add_failure(metadata, "wrong_type_item")
    if metadata["failure_type"]:
        return

    # 同名 task 按标准答案先后顺序逐个消耗，保持一对一配对。
    available: dict[str, deque[int]] = defaultdict(deque)
    for index, item in enumerate(expected):
        available[_normalized(item["task"])].append(index)
    paired_indices = []
    extra = []
    for item in items:
        candidates = available[_normalized(item["task"])]
        if not candidates:
            extra.append(item)
            continue
        index = candidates.popleft()
        paired_indices.append(index)
        standard = expected[index]
        if _normalized(item["owner"]) != _normalized(standard["owner"]):
            _add_failure(metadata, "wrong_owner")
        deadline = _normalized(item["deadline"])
        if deadline != _normalized(standard["deadline"]):
            _add_failure(metadata, "wrong_deadline")
            if deadline is not None and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", deadline) is None:
                metadata["deadline_bad_format"] = True

    paired = set(paired_indices)
    missing = [item for index, item in enumerate(expected) if index not in paired]
    if (len(missing) == len(extra) == 1
        and _normalized(missing[0]["owner"]) == _normalized(extra[0]["owner"])
        and _normalized(missing[0]["deadline"]) == _normalized(extra[0]["deadline"])):
        # 用户确认：R11 只记 wrong_task，两个计数字段保留为 0。
        _add_failure(metadata, "wrong_task")
    else:
        metadata["missing_count"] = len(missing)
        metadata["extra_count"] = len(extra)
        if missing:
            _add_failure(metadata, "missing_item")
        if extra:
            _add_failure(metadata, "extra_item")
    if not metadata["failure_type"]:
        metadata["order_violation"] = paired_indices != sorted(paired_indices)


def _evaluate_output(output: str, expected: dict[str, Any]) -> dict[str, Any]:
    """按流程顺序执行；早停后统一计算 correct 和 false_completion。"""
    data, metadata = _parse_output(output)
    if not metadata["failure_type"]:
        if data["status"] != expected["status"]:
            metadata["failure_type"] = ["false_ok" if data["status"] == "ok" else "false_refusal"]
        elif data["status"] == "cannot_complete" and data["items"]:
            metadata["failure_type"] = ["inconsistent_output"]
        else:
            _compare_items(data["items"], expected["items"], metadata)
    metadata["correct"] = not metadata["failure_type"]
    metadata["false_completion"] = metadata["claimed_ok"] and not metadata["correct"]
    return metadata


@scorer(metrics=[accuracy(), stderr()])
def office_scorer() -> Scorer:
    """Inspect 0.3.278：二值 Score，配 accuracy() 和 stderr()。"""
    async def score(state: TaskState, target: Target) -> Score:
        metadata = _evaluate_output(state.output.completion, state.metadata["expected_answer"])
        return Score(
            value=1 if metadata["correct"] else 0,
            explanation="通过" if metadata["correct"] else ", ".join(metadata["failure_type"]),
            metadata=metadata,
        )
    return score


@task
def office_bench() -> Task:
    dataset_path = Path(__file__).resolve().parents[1] / "data" / "tasks.jsonl"
    return Task(
        dataset=json_dataset(str(dataset_path), sample_fields=record_to_sample),
        solver=generate(),
        scorer=office_scorer(),
    )
