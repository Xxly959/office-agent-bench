# 作者本人补充的边界测试（至少 5 个）
import json
import unittest
from copy import deepcopy

from office_bench.task import _evaluate_output
from test_scorer import EXPECTED


class AuthorEdgeTests(unittest.TestCase):
    def test_example_B_string_null(self):
        # 1. 准备输入：复制标准答案，只改第三项 owner。
        output = deepcopy(EXPECTED)
        output["items"][2]["owner"] = "null"
        raw_output = json.dumps(output, ensure_ascii=False)

        # 2. 执行评分逻辑。不会调用模型 API。
        result = _evaluate_output(raw_output, EXPECTED)

        # 3. 检查提前按 R12 确定的期望。
        self.assertFalse(result["correct"])
        self.assertEqual(result["failure_type"], ["wrong_owner"])
        self.assertTrue(result["claimed_ok"])
        self.assertTrue(result["false_completion"])
        self.assertFalse(result["format_violation"])
        self.assertFalse(result["order_violation"])

    def test_N_status_with_spaces(self):
        # 判例 N / R6：status 不去首尾空白，" ok " 是无效枚举值。
        raw_output = '{"status":" ok ","items":[]}'
        result = _evaluate_output(raw_output, EXPECTED)

        self.assertTrue(result["parsed"])
        self.assertFalse(result["correct"])
        self.assertEqual(result["failure_type"], ["invalid_status"])
        self.assertFalse(result["claimed_ok"])
        self.assertFalse(result["false_completion"])
        self.assertFalse(result["format_violation"])
        self.assertFalse(result["order_violation"])

    def test_O_fenced_invalid_json(self):
        # 判例 O / R1：围栏合规，但内部 JSON 无效；围栏不算 extra_text。
        raw_output = '```json\n{"status":}\n```'
        result = _evaluate_output(raw_output, EXPECTED)

        self.assertFalse(result["parsed"])
        self.assertFalse(result["correct"])
        self.assertEqual(result["failure_type"], ["invalid_json"])
        self.assertTrue(result["fenced"])
        self.assertTrue(result["format_violation"])
        self.assertFalse(result["extra_text"])
        self.assertFalse(result["extractable_json"])
        self.assertIsNone(result["extracted_status"])
        self.assertFalse(result["claimed_ok"])
        self.assertFalse(result["false_completion"])

    def test_P_uppercase_fence(self):
        # 判例 P / R1、R3：大写 JSON 围栏不剥离，宽松提取仅作诊断。
        raw_output = '```JSON\n{"status":"ok","items":[]}\n```'
        result = _evaluate_output(raw_output, EXPECTED)

        self.assertFalse(result["parsed"])
        self.assertFalse(result["correct"])
        self.assertEqual(result["failure_type"], ["invalid_json"])
        self.assertFalse(result["fenced"])
        self.assertTrue(result["format_violation"])
        self.assertTrue(result["extra_text"])
        self.assertTrue(result["extractable_json"])
        self.assertEqual(result["extracted_status"], "ok")
        self.assertFalse(result["claimed_ok"])
        self.assertFalse(result["false_completion"])

    # 第 5 个测试留给你：沿用你已起的名字 test_example_D_。
    # 判例 D / R4：顶层多了 reason 字段。先按规则写期望，再构造输出。
    # def test_example_D_extra_reason(self):
    def test_D_extra_reason(self):
        raw_output = '{"status":"ok","reason":[],"items":[]}'
        result = _evaluate_output(raw_output, EXPECTED)
        self.assertTrue(result["parsed"])
        self.assertEqual(result["failure_type"], ["extra_key_top"])
        self.assertFalse(result["fenced"])
        self.assertFalse(result["extra_text"])
        self.assertFalse(result["extractable_json"])
        self.assertIsNone(result["extracted_status"])
        self.assertTrue(result["claimed_ok"])
        self.assertTrue(result["false_completion"])
        self.assertFalse(result["correct"])
