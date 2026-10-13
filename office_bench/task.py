from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample, json_dataset
from inspect_ai.scorer import Score, Scorer, Target, scorer
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


@scorer(metrics=[])
def placeholder_scorer() -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        # TODO（由项目负责人实现）：在此编写判分逻辑。
        # 黄金答案可从 state.metadata["expected_answer"] 读取。
        return Score(
            value="TODO",
            explanation="占位评分：尚未实现判分逻辑，不代表成功或失败。",
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
