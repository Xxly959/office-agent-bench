"""L2：预期逐条取自 PROJECT_SPEC 附录 C，不读取评分器结果生成预期。

只使用冻结任务；所有变异均作用于 deepcopy，不写入任务或历史结果。
"""

import hashlib
import json
import unittest
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from office_bench.task import _evaluate_output

ROOT = Path(__file__).resolve().parents[1]
TASK_SHA = "7e1c1edb039fa9d28894c747834196d64dfa29da797bfccec3e54c53117c7215"

# 固定预期来自作者提供的附录 C；不通过 _evaluate_output 推导。
EXPECTED = {
    "M01": (True, [], {"format_violation": False, "fenced": False,
                        "extra_text": False, "order_violation": False}),
    "M02": (True, [], {"fenced": True, "format_violation": True}),
    "M03": (True, [], {"fenced": True, "format_violation": True}),
    "M04": (True, [], {"order_violation": True}),
    "M05": (False, ["wrong_owner"], {}),
    "M06": (False, ["wrong_owner"], {}),
    "M07": (False, ["wrong_type_item"], {}),
    "M08": (False, ["wrong_deadline"], {"deadline_bad_format": True}),
    "M09": (False, ["wrong_deadline"], {}),
    "M10": (False, ["missing_item"], {"missing_count": 1}),
    "M11": (False, ["extra_item"], {"extra_count": 1}),
    "M12": (False, ["wrong_task"], {}),
    "M13": (False, ["missing_item", "extra_item"], {}),
    "M14": (False, ["extra_key_top"], {}),
    "M15": (False, ["missing_key_top"], {}),
    "M16": (False, ["invalid_status"], {}),
    "M17": (False, ["false_refusal"], {}),
    "M18": (False, ["false_ok"], {}),
    "M19": (False, ["inconsistent_output"], {}),
    "M20": (False, ["invalid_json"], {"extra_text": True, "extractable_json": True}),
    "M21": (False, ["extra_key_item"], {}),
    "M22": (False, ["missing_key_item"], {}),
    "M23": (False, ["wrong_type_top"], {}),
    "M24": (False, ["wrong_type_top"], {}),
    "M25": (False, ["invalid_json"], {"extra_text": False}),
    "M26": (True, [], {"format_violation": False, "fenced": False,
                        "extra_text": False, "order_violation": False}),
}


@dataclass
class Mutation:
    code: str
    variant: str
    raw: str | None = None
    claimed_ok: bool = False
    skip_reason: str | None = None
    diagnostics: dict = field(default_factory=dict)


def generate_mutations(record: dict) -> list[Mutation]:
    """每种变异选首个符合条件的项，未满足条件时记录跳过原因。"""
    gold = record["expected_answer"]
    items = gold["items"]
    claimed_ok = gold["status"] == "ok"
    cases = []

    def emit(code, data, variant="default", claimed=None, prefix="", suffix="",
             diagnostics=None):
        cases.append(Mutation(
            code, variant, prefix + json.dumps(data, ensure_ascii=False) + suffix,
            claimed_ok if claimed is None else claimed,
            diagnostics={} if diagnostics is None else diagnostics,
        ))

    def change(code, mutate, variant="default", claimed=None):
        output = deepcopy(gold)
        mutate(output)
        emit(code, output, variant, claimed)

    def skip(code, reason, variant="default"):
        cases.append(Mutation(code, variant, skip_reason=reason))

    emit("M01", gold)
    emit("M02", gold, prefix="```json\n", suffix="\n```")
    emit("M03", gold, prefix="```\n", suffix="\n```")
    if len(items) >= 2:
        change("M04", lambda output: output["items"].reverse())
    else:
        skip("M04", "items 少于 2 项")

    null_owner = next((i for i, item in enumerate(items) if item["owner"] is None), None)
    named_owner = next((i for i, item in enumerate(items) if item["owner"] is not None), None)
    if null_owner is not None:
        change("M05", lambda output: output["items"][null_owner].update(owner="null"))
    else:
        skip("M05", "金标没有 owner=null 的项")

    # 冻结文档中的人名候选；须同时满足出现在本题原文和不同于该项 owner。
    names = ("王敏", "陈宇", "李悦", "赵宁", "孙晴", "张楠", "Alex")
    replacement = next((name for name in names
                        if named_owner is not None
                        and name in record["document"]
                        and name != items[named_owner]["owner"]), None)
    if replacement is not None:
        change("M06", lambda output: output["items"][named_owner].update(owner=replacement))
    else:
        skip("M06", "没有有姓名的项，或原文没有另一个可替换人名")

    if items:
        change("M07", lambda output: output["items"][0].update(owner=123))
    else:
        skip("M07", "items 为空")
    dated = next((i for i, item in enumerate(items) if item["deadline"] is not None), None)
    if dated is not None:
        year, month, day = items[dated]["deadline"].split("-")
        chinese_date = f"{year}年{int(month)}月{int(day)}日"
        change("M08", lambda output: output["items"][dated].update(deadline=chinese_date))
        change("M09", lambda output: output["items"][dated].update(deadline=None))
    else:
        skip("M08", "金标没有非 null 的 deadline")
        skip("M09", "金标没有非 null 的 deadline")

    fabricated = {"owner": "L2虚构负责人", "task": "L2编造事项", "deadline": "2026-10-18"}
    if items:
        change("M10", lambda output: output["items"].pop(0))
    else:
        skip("M10", "items 为空")
    if claimed_ok:
        change("M11", lambda output: output["items"].append(deepcopy(fabricated)))
    else:
        skip("M11", "金标 cannot_complete，按附录 C 转由 M18 覆盖")
    if items:
        change("M12", lambda output: output["items"][0].update(task="L2改写：" + items[0]["task"]))
        change("M13", lambda output: output["items"][0].update(
            task="L2改写：" + items[0]["task"], owner="L2改写负责人"))
    else:
        skip("M12", "items 为空")
        skip("M13", "items 为空")

    change("M14", lambda output: output.update(reason="L2说明"))
    change("M15", lambda output: output.pop("items"))
    for status in ("OK", " ok "):
        change("M16", lambda output, status=status: output.update(status=status),
               variant=repr(status), claimed=False)
    if record["feasible"]:
        emit("M17", {"status": "cannot_complete", "items": []}, claimed=False)
        skip("M18", "feasible=true")
        skip("M19", "feasible=true")
    else:
        skip("M17", "feasible=false")
        emit("M18", {"status": "ok", "items": [deepcopy(fabricated)]}, claimed=True)
        emit("M19", {"status": "cannot_complete", "items": [deepcopy(fabricated)]}, claimed=False)

    emit("M20", gold, claimed=False, prefix="好的，结果如下：",
         diagnostics={"extracted_status": gold["status"]})
    if items:
        change("M21", lambda output: output["items"][0].update(reason="L2说明"))
        change("M22", lambda output: output["items"][0].pop("owner"))
    else:
        skip("M21", "items 为空")
        skip("M22", "items 为空")
    emit("M23", [], claimed=False)
    change("M24", lambda output: output.update(items={}))
    cases.append(Mutation("M25", "default", raw="", claimed_ok=False))
    if items:
        change("M26", lambda output: output["items"][0].update(
            task=" \t" + items[0]["task"] + " \t"), variant="task_whitespace")
        if named_owner is not None:
            change("M26", lambda output: output["items"][named_owner].update(
                owner=" \t" + items[named_owner]["owner"] + " \t"), variant="owner_whitespace")
        else:
            skip("M26", "没有字符串 owner，不能加首尾空白", variant="owner_whitespace")
    else:
        skip("M26", "items 为空")
    return cases


class MutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        task_bytes = (ROOT / "data/tasks.jsonl").read_bytes()
        if hashlib.sha256(task_bytes).hexdigest() != TASK_SHA:
            raise AssertionError("冻结任务集 SHA-256 不一致，停止 L2")
        cls.records = list(map(json.loads, task_bytes.decode().splitlines()))

    def test_generator_covers_every_author_mutation(self):
        # 防止生成器漏掉某种变异后，让评分断言因零样本而假通过。
        required = {f"M{number:02d}" for number in range(1, 27)}
        covered = set()
        for record in self.records:
            with self.subTest(task=record["id"]):
                cases = generate_mutations(record)
                self.assertEqual({case.code for case in cases}, required)
                self.assertEqual(len({(c.code, c.variant) for c in cases}), len(cases))
                for case in cases:
                    self.assertNotEqual(case.raw is None, case.skip_reason is None)
                    if case.raw is not None:
                        covered.add(case.code)
        # 防止某类变异被全数跳过；26 类均至少实际执行一次。
        self.assertEqual(covered, required)

    def test_generator_preserves_frozen_answers(self):
        for record in self.records:
            before = deepcopy(record)
            generate_mutations(record)
            self.assertEqual(record, before)

    def check_mutation(self, code):
        correct, failures, diagnostics = EXPECTED[code]
        for record in self.records:
            for case in generate_mutations(record):
                if case.code != code:
                    continue
                with self.subTest(task=record["id"], mutation=code, variant=case.variant):
                    if case.skip_reason is not None:
                        self.skipTest(case.skip_reason)
                    result = _evaluate_output(case.raw, record["expected_answer"])
                    self.assertIs(result["correct"], correct)
                    self.assertEqual(result["failure_type"], failures)
                    self.assertIs(result["claimed_ok"], case.claimed_ok)
                    # PROJECT_SPEC 6.2 的定义，预期不依赖评分器输出。
                    self.assertIs(result["false_completion"], case.claimed_ok and not correct)
                    for name, value in (diagnostics | case.diagnostics).items():
                        self.assertEqual(result[name], value, name)


def mutation_test(code):
    def test(self):
        self.check_mutation(code)
    test.__doc__ = f"附录 C {code}：逐题评分与作者预期一致。"
    return test


for mutation_code in EXPECTED:
    setattr(MutationTests, f"test_{mutation_code}", mutation_test(mutation_code))
