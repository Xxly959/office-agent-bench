import json
import unittest
from copy import deepcopy

from inspect_ai.model import ModelName, ModelOutput
from inspect_ai.scorer import Score, Target
from inspect_ai.solver import TaskState

from office_bench.task import _parse_output, office_scorer

EXPECTED = {
    "status": "ok",
    "items": [
        {"owner": "王敏", "task": "发送客户回访问卷", "deadline": "2026-10-16"},
        {"owner": "陈宇", "task": "归档培训签到表", "deadline": "2026-10-17"},
        {"owner": None, "task": "更新会议室预约规则", "deadline": "2026-10-18"},
    ],
}
VALID_JSON = json.dumps(EXPECTED, ensure_ascii=False)


class ScorerTests(unittest.IsolatedAsyncioTestCase):
    async def score_output(self, output: str, expected=None) -> Score:
        state = TaskState(
            model=ModelName("mockllm/model"),
            sample_id="fixture",
            epoch=1,
            input="",
            messages=[],
            output=ModelOutput(completion=output),
            metadata={"expected_answer": EXPECTED if expected is None else expected},
        )
        return await office_scorer()(state, Target(""))

    def assert_verdict(self, result, correct, failures, claimed_ok=True,
                       format_violation=False, order_violation=False,
                       missing_count=0, extra_count=0, deadline_bad_format=False):
        metadata = result.metadata or {}
        self.assertEqual(result.value, 1 if correct else 0)
        expected = {
            "correct": correct, "failure_type": failures,
            "claimed_ok": claimed_ok, "false_completion": claimed_ok and not correct,
            "format_violation": format_violation, "order_violation": order_violation,
            "missing_count": missing_count, "extra_count": extra_count,
            "deadline_bad_format": deadline_bad_format,
        }
        for field, value in expected.items():
            self.assertEqual(metadata.get(field), value, field)
        self.assertTrue({"parsed", "fenced", "extra_text", "extractable_json",
                         "extracted_status"}.issubset(metadata))

    async def test_A_fenced_json(self):
        result = await self.score_output(f"```json\n{VALID_JSON}\n```")
        metadata = result.metadata or {}
        self.assertIs(metadata.get("parsed"), True)
        self.assertIs(metadata.get("fenced"), True)
        self.assertIs(metadata.get("format_violation"), True)
        self.assertIs(metadata.get("claimed_ok"), True)
        self.assertEqual(metadata.get("failure_type"), [])
        self.assert_verdict(result, True, [], format_violation=True)

    async def test_B_string_null_owner(self):
        output = deepcopy(EXPECTED)
        output["items"][2]["owner"] = "null"
        self.assert_verdict(await self.score_output(json.dumps(output)), False, ["wrong_owner"])

    async def test_C_borrowed_owner(self):
        output = deepcopy(EXPECTED)
        output["items"][2]["owner"] = "陈宇"
        self.assert_verdict(await self.score_output(json.dumps(output)), False, ["wrong_owner"])

    async def test_D_extra_reason_claims_ok(self):
        output = VALID_JSON[:-1] + ',"reason":"说明"}'
        result = await self.score_output(output)
        metadata = result.metadata or {}
        self.assertIs(metadata.get("parsed"), True)
        self.assertIs(metadata.get("claimed_ok"), True)
        self.assertIn("extra_key_top", metadata.get("failure_type", []))
        self.assert_verdict(result, False, ["extra_key_top"])

    async def test_E_swapped_order(self):
        output = deepcopy(EXPECTED)
        output["items"][0], output["items"][1] = output["items"][1], output["items"][0]
        self.assert_verdict(await self.score_output(json.dumps(output)), True, [], order_violation=True)

    async def test_F_chinese_deadline(self):
        output = deepcopy(EXPECTED)
        output["items"][2]["deadline"] = "2026年10月18日"
        self.assert_verdict(await self.score_output(json.dumps(output)), False,
                            ["wrong_deadline"], deadline_bad_format=True)

    async def test_G_prefixed_json_is_only_diagnostic(self):
        result = await self.score_output("好的，结果如下：" + VALID_JSON)
        metadata = result.metadata or {}
        self.assertIs(metadata.get("parsed"), False)
        self.assertIs(metadata.get("extra_text"), True)
        self.assertIs(metadata.get("format_violation"), True)
        self.assertIs(metadata.get("claimed_ok"), False)
        self.assertIs(metadata.get("extractable_json"), True)
        self.assertEqual(metadata.get("extracted_status"), "ok")
        self.assertEqual(metadata.get("failure_type"), ["invalid_json"])
        self.assert_verdict(result, False, ["invalid_json"], claimed_ok=False, format_violation=True)

    async def test_H_missing_third_item(self):
        output = deepcopy(EXPECTED)
        output["items"] = output["items"][:2]
        self.assert_verdict(await self.score_output(json.dumps(output)), False,
                            ["missing_item"], missing_count=1)

    async def test_I_false_ok(self):
        output = {"status": "ok", "items": [deepcopy(EXPECTED["items"][0])]}
        expected = {"status": "cannot_complete", "items": []}
        self.assert_verdict(await self.score_output(json.dumps(output), expected), False, ["false_ok"])

    async def test_J_cannot_complete_with_items(self):
        output = {"status": "cannot_complete", "items": [deepcopy(EXPECTED["items"][0])]}
        expected = {"status": "cannot_complete", "items": []}
        self.assert_verdict(await self.score_output(json.dumps(output), expected), False,
                            ["inconsistent_output"], claimed_ok=False)

    async def test_K_false_refusal(self):
        output = '{"status":"cannot_complete","items":[]}'
        self.assert_verdict(await self.score_output(output), False, ["false_refusal"], claimed_ok=False)

    async def test_L_numeric_owner(self):
        output = deepcopy(EXPECTED)
        output["items"][0]["owner"] = 123
        self.assert_verdict(await self.score_output(json.dumps(output)), False, ["wrong_type_item"])

    async def test_M_rewritten_task(self):
        output = deepcopy(EXPECTED)
        output["items"][0]["task"] = "发送客户问卷"
        # 用户确认：R11 例外的漏项、多项计数都为 0。
        self.assert_verdict(await self.score_output(json.dumps(output)), False, ["wrong_task"])

    async def test_rule_based_boundaries(self):
        # 预期在运行前由规则 v1 + v1.1 推导，不读取评分器结果生成。
        # 每行：案例名、依据、完整输入、五个字段的预期值。
        fields = (
            "parsed", "fenced", "claimed_ok", "extra_text", "failure_type",
        )
        cases = [
            (
                "1_status_whitespace",
                "R6 / v1.1 N：status 不做 strip，不能声称 ok。",
                '{"status":" ok ","items":[]}',
                (True, False, False, False, ["invalid_status"]),
            ),
            (
                "2_fenced_invalid_object",
                "R1 / v1.1 O：剥离围栏后解析失败，围栏不算多余文字。",
                '```json\n{"status":}\n```',
                (False, True, False, False, ["invalid_json"]),
            ),
            (
                "3_fenced_non_json",
                "R2 / R1 / 流程第3步：解析失败，没有花括号，不满足 R3。",
                "```json\nnot json\n```",
                (False, True, False, False, ["invalid_json"]),
            ),
            (
                "4_unclosed_fence",
                "R1 / R3 / v1.1 P：围栏未闭合，花括号外还有围栏文字。",
                '```json\n{"status":"ok","items":[]}',
                (False, False, False, True, ["invalid_json"]),
            ),
            (
                "5_uppercase_fence",
                "R1 / R3 / v1.1 P：大写 JSON 不算围栏，花括号外有文字。",
                '```JSON\n{"status":"ok","items":[]}\n```',
                (False, False, False, True, ["invalid_json"]),
            ),
            (
                "6_top_level_list",
                "流程第4步：合法 JSON，但顶层不是对象。",
                "[]",
                (True, False, False, False, ["wrong_type_top"]),
            ),
            (
                "7_missing_items",
                "R4 / 流程第4步：先计算 claimed_ok，再检查缺失字段。",
                '{"status":"ok"}',
                (True, False, True, False, ["missing_key_top"]),
            ),
            (
                "8_items_object",
                "流程第4、5步：声称 ok，但 items 必须是列表。",
                '{"status":"ok","items":{}}',
                (True, False, True, False, ["wrong_type_top"]),
            ),
            (
                "P_opening_fence_trailing_space",
                "R1 / R3 / v1.1 P：开头行后的空格位于整段内部，不接受。",
                '```json \n{"status":"ok","items":[]}\n```',
                (False, False, False, True, ["invalid_json"]),
            ),
            (
                "P_internal_fence_line",
                "R1 / R3 / v1.1 P：内部另有围栏行，不算一个合规围栏块。",
                '```json\n```\n{"status":"ok","items":[]}\n```',
                (False, False, False, True, ["invalid_json"]),
            ),
            (
                "P_closing_fence_trailing_whitespace",
                "R2 / v1.1 P：整段先 strip，结尾围栏行后的空白被忽略。",
                '```json\n{"status":"ok","items":[]}\n``` \t\n',
                (True, True, True, False, []),
            ),
        ]
        for name, rule, output, expected in cases:
            with self.subTest(case=name, rule=rule):
                # 保留已有边界输入和预期；只验证原来第 1—5 步的解析字段。
                _, metadata = _parse_output(output)
                for field, value in zip(fields, expected, strict=True):
                    if isinstance(value, bool):
                        self.assertIs(metadata.get(field), value, field)
                    else:
                        self.assertEqual(metadata.get(field), value, field)
