"""从 Inspect 0.3.278 原始日志导出逐次结果、事实汇总与运行清单。

API 依据：references/inspect_ai tag 0.3.278，log/_file.py 的
read_eval_log，log/_log.py 的 EvalSample/EvalStats/EvalSpec，
core/_model_output.py 的 ModelUsage。此脚本不调用模型。
"""

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from zoneinfo import ZoneInfo

from inspect_ai.log import read_eval_log
from inspect_ai.scorer import CORRECT, INCORRECT


TASK_SHA = "7e1c1edb039fa9d28894c747834196d64dfa29da797bfccec3e54c53117c7215"
FIELDS = [
    "id", "epoch", "difficulty", "family", "feasible", "correct", "claimed_ok",
    "false_completion", "failure_type", "format_violation", "order_violation",
    "missing_count", "extra_count", "model_output",
]
FAILURES = [
    "invalid_json", "wrong_type_top", "missing_key_top", "extra_key_top",
    "invalid_status", "false_ok", "false_refusal", "inconsistent_output",
    "wrong_type_item", "missing_key_item", "extra_key_item", "wrong_owner",
    "wrong_deadline", "missing_item", "extra_item", "wrong_task",
]


def local_time(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Shanghai")).isoformat()


def export(log_path: Path, execution_path: Path, output_dir: Path) -> None:
    if version("inspect-ai") != "0.3.278":
        raise ValueError("Inspect 版本必须为 0.3.278")
    task_path = Path(__file__).resolve().parents[1] / "data/tasks.jsonl"
    checksum = hashlib.sha256(task_path.read_bytes()).hexdigest()
    if checksum != TASK_SHA:
        raise ValueError(f"任务集校验失败：{checksum}")
    records = [json.loads(line) for line in task_path.read_text().splitlines()]
    expected_pairs = {(record["id"], epoch) for record in records for epoch in range(1, 4)}
    execution = json.loads(execution_path.read_text())
    if execution["returncode"] != 0:
        raise ValueError("正式运行进程未成功，禁止生成完成汇总")
    if execution["sha_before"] != TASK_SHA or execution["sha_after"] != TASK_SHA:
        raise ValueError("正式运行前后任务集校验失败")
    log = read_eval_log(log_path)
    if log.status != "success" or log.error is not None:
        raise ValueError(f"日志状态不是 success：{log.status}，error={log.error}")
    if log.eval.model != "deepseek/deepseek-flash" or log.eval.config.epochs != 3:
        raise ValueError("日志模型或 epochs 与本次要求不符")
    if log.eval.packages.get("inspect_ai") != "0.3.278":
        raise ValueError("日志记录的 Inspect 版本不是 0.3.278")

    rows = []
    for sample in sorted(log.samples or [], key=lambda item: (str(item.id), item.epoch)):
        if sample.error is not None:
            raise ValueError(f"样本 {sample.id}/{sample.epoch} 有错误：{sample.error}")
        if not sample.scores or len(sample.scores) != 1:
            raise ValueError(f"样本 {sample.id}/{sample.epoch} 必须恰有一个评分")
        score = next(iter(sample.scores.values()))
        metadata = score.metadata or {}
        if score.value not in (CORRECT, INCORRECT):
            raise ValueError(f"样本 {sample.id}/{sample.epoch} 不是二值评分")
        if metadata["correct"] != (score.value == CORRECT):
            raise ValueError(f"样本 {sample.id}/{sample.epoch} value 与 correct 冲突")
        if metadata["false_completion"] != (metadata["claimed_ok"] and not metadata["correct"]):
            raise ValueError(f"样本 {sample.id}/{sample.epoch} false_completion 冲突")
        if metadata["correct"] and metadata["failure_type"]:
            raise ValueError(f"样本 {sample.id}/{sample.epoch} 通过但有失败类型")
        row = {"id": sample.id, "epoch": sample.epoch}
        row.update({key: sample.metadata[key] for key in ("difficulty", "family", "feasible")})
        row.update({key: metadata[key] for key in FIELDS[5:-1]})
        row["model_output"] = sample.output.completion
        rows.append(row)
    pairs = {(row["id"], row["epoch"]) for row in rows}
    if len(rows) != 24 or len(pairs) != 24 or pairs != expected_pairs:
        raise ValueError(f"题目×epoch 不完整或重复：行数={len(rows)}，唯一配对数={len(pairs)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "stage1_runs.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            serialized = dict(row)
            serialized["failure_type"] = json.dumps(row["failure_type"], ensure_ascii=False)
            for key in ("feasible", "correct", "claimed_ok", "false_completion", "format_violation", "order_violation"):
                serialized[key] = str(row[key]).lower()
            writer.writerow(serialized)
    with csv_path.open(encoding="utf-8", newline="") as stream:
        csv_count = sum(1 for _ in csv.DictReader(stream))
    if csv_count != len(rows) or csv_count != 24:
        raise ValueError(f"CSV 行数核对失败：{csv_count}，日志行数={len(rows)}")

    failures = Counter(failure for row in rows for failure in row["failure_type"])
    per_task = Counter(row["id"] for row in rows if row["correct"])
    summary = [
        "# 第一阶段首次运行事实汇总", "",
        f"- 总样本次数：{len(rows)}", f"- CSV 数据行数：{csv_count}",
        f"- 总通过次数：{sum(row['correct'] for row in rows)}/{len(rows)}", "",
        "| id | 通过次数 |", "| --- | --- |",
    ]
    summary += [f"| {record['id']} | {per_task[record['id']]}/3 |" for record in records]
    summary += [
        "", f"- claimed_ok 次数：{sum(row['claimed_ok'] for row in rows)}",
        f"- false_completion 次数：{sum(row['false_completion'] for row in rows)}",
        f"- false_completion 中属于 false_ok 的次数：{sum(row['false_completion'] and 'false_ok' in row['failure_type'] for row in rows)}",
        f"- format_violation 次数：{sum(row['format_violation'] for row in rows)}",
        f"- order_violation 次数：{sum(row['order_violation'] for row in rows)}", "",
        "| failure_type | 次数 |", "| --- | --- |",
    ]
    summary += [f"| {failure} | {failures[failure]} |" for failure in FAILURES]
    unknown = set(failures) - set(FAILURES)
    if unknown:
        raise ValueError(f"出现未知失败类型：{sorted(unknown)}")
    (output_dir / "stage1_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    total_tokens = sum(usage.total_tokens for usage in log.stats.model_usage.values())
    elapsed = (datetime.fromisoformat(log.stats.completed_at) - datetime.fromisoformat(log.stats.started_at)).total_seconds()
    manifest = [
        "# 第一阶段首次运行清单", "",
        f"- 进程开始时间（Asia/Shanghai）：{execution['started_at']}",
        f"- 进程结束时间（Asia/Shanghai）：{execution['completed_at']}",
        f"- Inspect 日志开始时间（Asia/Shanghai）：{local_time(log.stats.started_at)}",
        f"- Inspect 日志结束时间（Asia/Shanghai）：{local_time(log.stats.completed_at)}",
        f"- 工作目录：{execution['cwd']}", f"- 模型名：{log.eval.model}",
        f"- Provider base URL：{log.eval.model_base_url}",
        f"- Inspect 版本：{log.eval.packages['inspect_ai']}",
        f"- 每题重复次数：{log.eval.config.epochs}",
        f"- 运行前任务集 shasum：{execution['sha_before']}",
        f"- 运行后任务集 shasum：{execution['sha_after']}",
        f"- 导出时任务集 shasum：{checksum}",
        f"- 日志文件：{log_path.as_posix()}",
        "- 命令原始输出：results/run_stage1_output.txt",
        f"- 总 token 数（日志 model_usage.total_tokens 合计）：{total_tokens}",
        f"- Inspect 日志耗时（秒）：{elapsed:.6f}",
        f"- 进程耗时（秒）：{execution['elapsed_seconds']:.6f}",
        f"- 日志样本次数：{len(rows)}", "", "完整命令：", "", "```sh",
        execution["command"], "```", "",
    ]
    (output_dir / "run_manifest_stage1.md").write_text("\n".join(manifest), encoding="utf-8")
    print(f"log status={log.status}; rows={len(rows)}; unique id×epoch={len(pairs)}; csv rows={csv_count}")
    print(f"correct={sum(row['correct'] for row in rows)}/24; total_tokens={total_tokens}; elapsed_seconds={elapsed:.6f}")
    print(csv_path)
    print(output_dir / "stage1_summary.md")
    print(output_dir / "run_manifest_stage1.md")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--execution", type=Path, default=Path("results/run_execution_stage1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    args = parser.parse_args()
    export(args.log, args.execution, args.output_dir)


if __name__ == "__main__":
    main()
