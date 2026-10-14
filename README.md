# Office Agent Bench

这是一个正在进行的办公任务评测项目。当前工程覆盖 8 条文本任务、确定性 JSON 评分、Inspect 日志导出和离线复核；文件、工具和沙箱任务尚未实现。以下方法与运行事实由 Codex 整理，项目动机、个人分析与最终报告由作者撰写定稿。

## 当前结果与方法

2026-10-13 使用 `deepseek/deepseek-flash`，8 题各运行 3 次，24/24 通过；格式违规、顺序违规和误报完成均为 0。误报完成按全部有效样本为 0/24，按声称完成的样本为 0/21。当前只有 1 条 cannot_complete 任务，不做跨模型或统计显著性结论。

评分按 [v1 与 v1.1 规则](docs/scorer_rules.md)执行，整题二值。围栏可以剥离但记录违规，事项顺序不影响内容正确；其他结构和字段错误按成文规则判定。claimed_ok 与 correct 分开记录，false_completion = claimed_ok 且 not correct。现实现的 Score.value 为数字 1/0，首次日志的 C/I 表示保留，导出器兼容两者。

原始日志、逐次 CSV 和自动汇总位于 [results](results/)。[工程复核与预测对照](docs/stage1_audit.md)记录了实际与预测的差距、运行后的修正及复现局限。[人工复核材料](docs/review_stage1.md)待作者填写；尚无已确认的分歧样本。

## 复现存档结果

需要 Python 与 `requirements.txt` 中的 Inspect 版本；当前本机验证使用 Python 3.14.6。首次准备环境：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

在仓库根目录用一条命令复核存档：

```sh
.venv/bin/python scripts/reproduce_stage1.py
```

它运行完整测试和数据验证，检查冻结数据及原始日志哈希，逐条核对模型实际输入，重新计算全部评分诊断，导出 CSV 和汇总，并与首次结果逐字节比较。输出到 `results/reproduced_stage1/`，任一检查失败即以非零状态退出。无需 API key，也不会调用模型。首次运行命令见 [运行清单](results/run_manifest_stage1.md)；再运行模型会发生 API 费用，也可能产生不同输出。

首次日志有 dirty=True，且 temperature、最大 token 与 thinking 参数未显式固定。因此这里只承诺存档结果可离线复核，不承诺重复 API 调用得到相同文本。只固定了直接依赖 Inspect，完整的传递依赖锁定及干净环境验证留待第二阶段工程化。

## 项目结构

`data/` 存放冻结任务、哈希和数据说明；`docs/` 存放规则、预测及复核材料；`office_bench/` 定义任务和确定性评分器；`scripts/` 校验数据、导出与复现；`tests/` 检查规则判例和复现失败路径；`results/` 保留首次日志、命令原始输出和生成的表格。

## 作者写作与后续工作

作者还需补充项目动机、对预测偏差的解释、独立复核结论与个人报告。第二阶段先确定家族配额、不可完成的语义和文件检查规则，再写任务及代码；第一阶段数据继续冻结。

## 第一阶段已知局限

- 只有 `office_007` 的标准答案为 `cannot_complete`。不可完成场景的虚假完成率仅覆盖一个任务，信息量有限；第二阶段优先增加不可完成任务。
- 当前没有任何任务测试 `deadline` 为 `null` 的情形。
- 事项名称都带 `「」`，指令要求复制原文，抽取更接近模式匹配。这是为了让第一阶段评分可确定而做的取舍，第二阶段考虑放宽。
- 会议名称不在输出结构中；`office_001` 中的会议名称仅为背景信息，输出项只包含 `owner`、`task`、`deadline`。

## 任务冻结规则

第一阶段的 8 条任务自此冻结。模型全对或全错均如实记录，不据此回头调整题目。只有确认存在真正的文档歧义时才修订，并记录修订原因。
