"""离线复核第一阶段：测试、冻结哈希、输入边界、重新评分、日志导出。

不调用模型 API，不安装依赖，不覆盖首次运行结果。
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from inspect_ai.log import read_eval_log
from office_bench.task import _evaluate_output
from scripts.export_results import TASK_SHA, export

LOG = ROOT / "results/logs/2026-10-13T12-43-57-00-00_office-bench_MvoRpVQKoEnCfdUebzPJ2H.eval"
LOG_SHA = "057dda30de763986005c026dba16f609c007c26deffd3bd549f35588596125c2"
ARCHIVE_HASHES = {
    LOG: LOG_SHA,
    ROOT / "results/run_execution_stage1.json": "9bec14f959d5cfed08eb84e6be74f5ef4f9aa3af4914b6c8197f56b890e78ed7",
    ROOT / "results/run_stage1_output.txt": "10124caac1dec69fcd5499f93ad966c63e29b267be9d51eb55f6ebf1ef38980f",
}


def verify_hash(path: Path, expected: str) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"SHA-256 不一致：{path.name}: {actual}; expected={expected}")


def audit_sample(sample, record: dict) -> None:
    expected_input = f"【指令】\n{record['instruction']}\n\n【文档】\n{record['document']}"
    inputs = [message for message in sample.messages if message.role != "assistant"]
    if len(inputs) != 1 or inputs[0].role != "user" or inputs[0].content != expected_input:
        raise ValueError(f"模型输入与冻结任务不一致：{sample.id}/{sample.epoch}")
    if not sample.scores or len(sample.scores) != 1:
        raise ValueError(f"评分数不一致：{sample.id}/{sample.epoch}")
    saved = next(iter(sample.scores.values())).metadata or {}
    fresh = _evaluate_output(sample.output.completion, record["expected_answer"])
    if fresh != saved:
        fields = sorted(key for key in fresh.keys() | saved.keys() if fresh.get(key) != saved.get(key))
        raise ValueError(f"重新评分不一致：{sample.id}/{sample.epoch}: {fields}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/reproduced_stage1")
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir == ROOT / "results":
        raise ValueError("请选择独立输出目录，保留首次运行结果")
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                   cwd=ROOT, check=True)
    subprocess.run([sys.executable, "scripts/validate_tasks.py"], cwd=ROOT, check=True)
    verify_hash(ROOT / "data/tasks.jsonl", TASK_SHA)
    for path, checksum in ARCHIVE_HASHES.items():
        verify_hash(path, checksum)
    records = {record["id"]: record for record in map(json.loads, (ROOT / "data/tasks.jsonl").read_text().splitlines())}
    log = read_eval_log(LOG)
    for sample in log.samples or []:
        audit_sample(sample, records[str(sample.id)])
    # exporter 另检查 8 × 3 配对完整性、运行状态、Score 与 correct 一致性。
    export(LOG, ROOT / "results/run_execution_stage1.json", output_dir)
    for name in ("stage1_runs.csv", "stage1_summary.md"):
        if (ROOT / "results" / name).read_bytes() != (output_dir / name).read_bytes():
            raise ValueError(f"重新导出与首次结果不一致：{name}")
    print("PASS: 冻结任务、日志及运行凭证哈希、24 次输入、全部评分诊断字段、CSV 和汇总一致。")
    print(f"首次运行代码状态：{log.eval.revision}")
    print("注意：这是存档日志的离线复核；模型再次运行可能产生不同输出。")


if __name__ == "__main__":
    main()
