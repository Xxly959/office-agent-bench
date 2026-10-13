# 第一阶段阅读笔记

选取样本 ID：`boolq_645b568f`

## 1. 到底向模型发送了什么？

收到了 message，没有 target。

user 消息包括一段提示词、passage 和 question。

## 2. Target 从哪里来？

`record["answer"]` 转换后存入 `target`。这条样本的 `target` 是 `No`，对应原始 `answer` 为 `False`。

## 3. Solver 做了什么？

根据 user 消息生成 assistant 回复，没有计算分数。

Messages 中有一条 assistant 回复，没有工具调用或 tool 消息。

## 4. Scorer 比较了什么？

要和 `target` 比较，符合就是 `C`，不符合就是 `I`。

主体只能是 yes/no，不能拆开，不能出现其他单词，主体前后有标点无所谓。

## 5. 分数保存在哪里？

日志文件：`logs/2026-10-11T13-41-38-00-00_boolq_TPWEDWSNT9h5sFGyXZZ8nL.eval`。

accuracy 描述的是整次评测。两个正确，除以三个样本：`2 ÷ 3 ≈ 0.667`。

## 后续参考

从单轮 BoolQ 评测扩展到 Office agent 评测时，参考 [Agent evals 阅读笔记与项目备忘](agent_evals_reading_notes.md)。该笔记区分原文要点、当前项目事实和后续设计建议。
