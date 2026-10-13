import unittest

from inspect_ai.model import ModelName, ModelOutput
from inspect_ai.scorer import INCORRECT, Score, Target
from inspect_ai.solver import TaskState

from office_bench.task import placeholder_scorer

VALID_JSON = (
    '{"status":"ok","items":[{"owner":"Alex",'
    '"task":"发送会议通知","deadline":"2026-10-14"}]}'
)


class ScorerTests(unittest.IsolatedAsyncioTestCase):
    async def score_output(self, output: str) -> Score:
        state = TaskState(
            model=ModelName("mockllm/model"),
            sample_id="fixture",
            epoch=1,
            input="",
            messages=[],
            output=ModelOutput(completion=output),
        )
        return await placeholder_scorer()(state, Target(""))

    async def test_A_fenced_json(self):
        result = await self.score_output(f"```json\n{VALID_JSON}\n```")
        metadata = result.metadata or {}
        self.assertIs(metadata.get("parsed"), True)
        self.assertIs(metadata.get("fenced"), True)
        self.assertIs(metadata.get("format_violation"), True)
        self.assertIs(metadata.get("claimed_ok"), True)
        self.assertEqual(metadata.get("failure_type"), [])
        self.assertEqual(result.value, INCORRECT)
        self.assertIn("后续步骤未实现", result.explanation or "")

    async def test_D_extra_reason_claims_ok(self):
        output = VALID_JSON[:-1] + ',"reason":"说明"}'
        result = await self.score_output(output)
        metadata = result.metadata or {}
        self.assertIs(metadata.get("parsed"), True)
        self.assertIs(metadata.get("claimed_ok"), True)
        self.assertIn("extra_key_top", metadata.get("failure_type", []))
        self.assertEqual(result.value, INCORRECT)

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
        self.assertEqual(result.value, INCORRECT)

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
                result = await self.score_output(output)
                self.assertIsNotNone(result.metadata)
                metadata = result.metadata or {}
                for field, value in zip(fields, expected, strict=True):
                    if isinstance(value, bool):
                        self.assertIs(metadata.get(field), value, field)
                    else:
                        self.assertEqual(metadata.get(field), value, field)
                # 第6步及以后尚未实现，Score.value 仍是占位的 INCORRECT。
                self.assertEqual(result.value, INCORRECT)
