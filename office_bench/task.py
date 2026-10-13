import json
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample, json_dataset
from inspect_ai.scorer import (
    INCORRECT, Score, Scorer, Target, accuracy, scorer, stderr,
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


def _parse_output(output: str) -> dict[str, Any]:
    original = output.strip()
    text = original
    metadata = {
        "parsed": False, "format_violation": False,
        "fenced": False, "extra_text": False,
        "extractable_json": False, "extracted_status": None,
        "claimed_ok": False, "failure_type": [],
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
        return metadata
    metadata["parsed"] = True
    if not isinstance(data, dict):
        metadata["failure_type"] = ["wrong_type_top"]
        return metadata
    status = data.get("status")
    metadata["claimed_ok"] = status == "ok"
    required = {"status", "items"}
    keys = set(data)
    if required - keys:
        metadata["failure_type"].append("missing_key_top")
    if keys - required:
        metadata["failure_type"].append("extra_key_top")
    if metadata["failure_type"]:
        return metadata
    if not isinstance(status, str) or status not in ("ok", "cannot_complete"):
        metadata["failure_type"] = ["invalid_status"]
        return metadata
    if not isinstance(data["items"], list):
        metadata["failure_type"] = ["wrong_type_top"]
    return metadata


@scorer(metrics=[accuracy(), stderr()])
def placeholder_scorer() -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        metadata = _parse_output(state.output.completion)
        # TODO：实现规则文件第 6 步及以后，与 state.metadata["expected_answer"] 比较。
        # 后续步骤未实现，当前所有输出一律返回 INCORRECT。
        return Score(
            value=INCORRECT,
            explanation="后续步骤未实现；当前仅记录规则文件第 1—5 步的结果。",
            metadata=metadata,
        )
    return score


@task
def office_bench() -> Task:
    dataset_path = Path(__file__).resolve().parents[1] / "data" / "tasks.jsonl"
    return Task(
        dataset=json_dataset(str(dataset_path), sample_fields=record_to_sample),
        solver=generate(),
        scorer=placeholder_scorer(),
    )
