# 第一阶段数据说明

`tasks.jsonl` 是 UTF-8 JSON Lines，8 条人工办公任务。冻结数据提交为 `6d26c33`，SHA-256 见 `tasks.sha256`；本阶段不因模型结果调整任务。

每条包含 `id`、`difficulty`、`family`、`feasible`、`document`、`instruction`、`expected_answer`、`why_hard`。难度分布为 easy 4、hard 2、adversarial 2。家族为事项抽取和表格筛选。

标准答案结构为 `{status, items}`；item 为 `{owner, task, deadline}`。`owner` 和 `deadline` 允许 JSON null；`task` 必须是字符串。第一阶段尚无 deadline 为 null 的任务，评分规则的覆盖不能等同于任务覆盖。

参考日期写在任务文档中，不使用运行当天日期。事项抽取通过「」标记事项名，表格任务复制事项列。`office_007` 是唯一 `feasible=false` 样本：它没有符合要求的待办，按 v1 返回 `cannot_complete`。这里的状态含义是“无符合条件事项”，不等同于工具环境下“缺少资源所以无法执行”。

第一阶段 `record_to_sample` 只把 instruction 和 document 写入 user 消息。expected_answer 位于 Inspect 的宿主 metadata，用于评分；本阶段没有模型工具，也没有文件沙箱。离线复核逐条比较日志中的完整输入与上述构造，不仅搜索字段名称。第二阶段不得把标准答案、检查器配置或完整仓库挂载到模型沙箱。

运行 `python scripts/reproduce_stage1.py` 可验证冻结任务及原始日志哈希，并复核输入和评分。这里的数据哈希只认证文件未变，不证明标准答案已经得到独立人工验证。
