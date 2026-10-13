# 评分规则 v1

## 0. 总原则
1. 评分必须是确定性的：同一输出永远得到同一分数，评分器里不使用 LLM。
2. "内容是否正确"和"格式是否合规"分开记录，不混成一个分数。
3. "模型是否声称完成"和"结果是否正确"分开存储，误报完成由两者推出。
4. 能机械修好、不改变含义的（围栏、顺序），通过但记录违规；含义变了、无法确定、或违反"仅含"之类强限定的，不通过。围栏是唯一允许的格式宽容，其余格式问题一律严格。
5. `failure_type` 只在 `correct = false` 时才有值；违规（围栏、顺序）只记标记，不记失败类型。

## 1. 解析与判定流程

按顺序执行。第 3 到 7 步命中即结束，一个样本只记一个主失败类型，方便统计；第 8 步可以同时记录多个。

1. 取模型最终输出原文，去掉首尾空白。
2. 若整段恰好是一个围栏块（以 ``` 或 ```json 开头、以 ``` 结尾），去掉围栏，记 `format_violation = true`、`fenced = true`。
3. 用 JSON 解析。失败 → R1，`parsed = false`，`claimed_ok = false`，结束。
   - 若失败，且原文中有一对花括号、前后另有文字，额外记 `extra_text = true`（R3）。尝试取"第一个 { 到最后一个 }"解析，成功则记 `extractable_json = true`，并记 `extracted_status`。这两项只作诊断，**不改变判定**。
4. 顶层必须是 JSON 对象，否则记 `wrong_type_top`，结束。
   - 在此处计算 `claimed_ok`：顶层是对象，且其中 `status` 的值等于 `"ok"`，即为真。之后无论其他部分对错，都不再改变它。
   - 顶层键集合必须恰好等于 {status, items}，否则 R4（`missing_key_top` / `extra_key_top`，可同时记录），结束。
5. `status` 必须是字符串 `ok` 或 `cannot_complete`，否则 R6（`invalid_status`），结束。`items` 必须是列表，否则 `wrong_type_top`，结束。
6. `status` 与标准答案不同 → R7，结束。
   - 标准答案 `cannot_complete`、模型 `ok`：记 `false_ok`。
   - 标准答案 `ok`、模型 `cannot_complete`：记 `false_refusal`。
7. `status` 为 `cannot_complete` 且 `items` 非空 → R8（`inconsistent_output`），结束。（能走到这一步，说明标准答案也是 `cannot_complete`。）
8. 比较 items：
   1. **结构检查。** 每个 item 必须是对象，否则 `wrong_type_item`；键集合必须恰好等于 {owner, task, deadline}，否则 R5（`missing_key_item` / `extra_key_item`）；owner 只能是字符串或 null，task、deadline 在模型输出中必须是字符串（deadline 也允许 null），否则 `wrong_type_item`。任何结构失败都记录并结束，因为无法再配对。
   2. **配对。** 按 `task` 字符串配对（task 要求逐字复制，是最可靠的钥匙）。同名 task 出现多次时，一对一消耗。
   3. **已配对的项**：比较 owner（R12，`wrong_owner`）和 deadline（R13，`wrong_deadline`），可同时记录。
   4. **未配对的项**：标准答案里没配上的是漏项，模型里没配上的是多项（R9）。唯一例外见 R11：恰好一漏一多，且 owner 与 deadline 都和对方相同，则只记 `wrong_task`，不记漏项和多项。
9. 若第 8 步没有任何失败，则 `correct = true`。再检查顺序：已配对的模型 items 的先后顺序与标准答案不同，则记 `order_violation = true`（R10），不影响 `correct`。

**字符串比较的统一约定：** 所有字符串在比较前只去掉首尾空白，其余逐字比较，不区分的情形不放宽（例如 `OK` 不等于 `ok`）。`null` 只与 `null` 相等。

## 2. 规则表

判法说明：「错误」表示该样本 `correct = false`；「通过但记录违规」表示 `correct` 不受影响，只记录违规标记。

| 编号 | 情形 | 判法 | 记录 | 理由 |
|---|---|---|---|---|
| R1 | 无法解析为 JSON | 错误；`claimed_ok = false` | `parsed = false`；failure_type `invalid_json` | 指令要求只返回 JSON 对象，无法解析就没有可评估的答案；没有可读的 status，所以不算"声称完成"，也就不计入误报完成，而是单独的格式失败 |
| R2 | 带 Markdown 围栏 | 剥离围栏后继续判内容；通过但记录违规 | `format_violation = true`，`fenced = true` | 评分分为格式和内容两部分；指令写了"不要 Markdown"，所以围栏是违规，但内容是否正确要单独统计；剥离后 `claimed_ok` 照常按 status 计算 |
| R3 | JSON 前后有多余文字 | 按 R1 处理：错误 | `parsed = false`，`format_violation = true`，`extra_text = true`；failure_type `invalid_json`；诊断 `extractable_json` | 第一阶段只剥围栏，不做宽松提取，因为宽松提取会掩盖模型的格式毛病，夹带多个 JSON 时还可能取错 |
| R4 | 顶层字段缺失或多余 | 错误 | failure_type `missing_key_top` / `extra_key_top` | 指令写明"顶层仅含 status 和 items"，模型违反了明确约束；缺失和多余分开记录，保证顶层结构的唯一性 |
| R5 | item 字段缺失或多余 | 错误 | failure_type `missing_key_item` / `extra_key_item` | 指令写明"每个 item 仅含 owner、task、deadline"，同上 |
| R6 | status 不是 `ok` / `cannot_complete`（含大小写不同，如 `OK`、`done`、`无法完成`） | 错误；`claimed_ok = false` | failure_type `invalid_status` | status 是枚举值，不存在"意思差不多"；写错就是违反输出协议 |
| R7 | status 与标准答案不同 | 整题错误，不再比较 items | failure_type `false_ok`（标准答案 cannot_complete、模型 ok）或 `false_refusal`（标准答案 ok、模型 cannot_complete） | status 是最高层的结论，它错了，items 再对也没有意义；两个方向的错误含义不同，分开记录：`false_ok` 是编造，`false_refusal` 是把能做的事说成做不了 |
| R8 | `status = cannot_complete` 但 `items` 非空 | 错误 | failure_type `inconsistent_output` | 自相矛盾的输出不能当作任何一种有效答案 |
| R9 | items 数量不同（漏项、多项） | 错误 | failure_type `missing_item` / `extra_item`；`missing_count`、`extra_count` | 漏项和多项是失败分析最有价值的两类，要分开计数 |
| R10 | items 顺序与"按首次出现顺序"不同 | 按配对结果比较内容；内容全对则通过但记录违规 | `order_violation = true` | 顺序是次要约束，不该把内容全对的答案判成失败；但指令明确要求了顺序，所以必须记录违规 |
| R11 | task 与标准答案不完全一致 | 错误；逐字比较，仅去首尾空白 | failure_type `wrong_task`（仅当恰好一漏一多且 owner、deadline 相同）；其他情形记为漏项加多项 | 指令要求"复制引号内的事项名称，不要改写"，严格比较有依据；因为按 task 配对，task 写错的项在配对时就显示为漏项和多项，用此例外把"只是改写了名称"这种情形识别出来 |
| R12 | 已配对项的 owner 不一致，包括：标准答案为 `null` 而模型写成 `"null"`、空串、"无"、借用他人姓名；或标准答案为姓名而模型写成别的姓名、称呼（如"王总"、"Alex 先生"） | 错误；只有 JSON 的 `null`（标准答案为 null 时）或与原文完全相同的姓名才通过 | failure_type `wrong_owner` | 指令要求"使用原文人名，未确定负责人时必须为 null，不能猜测"；008 就靠这一条测试模型是否抵抗补全的冲动 |
| R13 | 已配对项的 deadline 与标准答案不同（含格式不是 `YYYY-MM-DD`） | 错误；直接比较字符串，不替模型转换格式 | failure_type `wrong_deadline`；若格式不符 `YYYY-MM-DD`，另记诊断 `deadline_bad_format = true` | 003 考的就是模型会不会把中文日期转换成统一格式，评分器替它转换就失去了测试意义 |

## 3. 每次评分记录的字段

| 字段 | 含义 |
|---|---|
| `parsed` | 是否成功解析出 JSON（剥离围栏后） |
| `format_violation` | 是否违反"只返回 JSON"（围栏、前后多余文字） |
| `fenced` / `extra_text` | 具体是哪种格式违规 |
| `extractable_json` / `extracted_status` | 诊断：R3 情形下能否宽松提取出 JSON、其 status 是什么。**不参与判定** |
| `order_violation` | 是否违反顺序要求 |
| `claimed_ok` | 声称完成：已解析，顶层是对象，且 `status == "ok"`（见流程第 4 步） |
| `correct` | 内容是否与标准答案一致（顺序除外，见 R10） |
| `failure_type` | 失败类型，可以有多个；`correct = true` 时为空 |
| `missing_count` / `extra_count` | 漏项数、多项数 |
| `false_completion` | 误报完成 = `claimed_ok` 且 `not correct` |

写入 Inspect 的 `Score`：`value` 取 `correct`（1 或 0），上面其余字段放入 `metadata`。

**两个"误报"名称的区别：** `false_completion` 是总指标，凡是声称完成却不正确都算，包括内容错、字段错、编造。`false_ok` 是其中一个子类，专指标准答案本应是 `cannot_complete`、模型却说 `ok`。

## 4. 整题还是部分分

第一阶段整题二值：`correct` 为真才算通过，只要有一项错，整题就是 0。漏项数、多项数另行记录，供第五阶段的失败分析使用。

## 5. 判例

判定只有三种：**通过** / **不通过** / **通过但记录违规**。

| 案例 | 模型输出的情况 | 判定 | 对应规则 | 记录的违规标记 | failure_type（仅不通过时） | 理由 |
|---|---|---|---|---|---|---|
| A | 内容完全正确，外面包了 ```json 围栏 | 通过但记录违规 | R2 | `format_violation`，`fenced` | 无 | 去掉围栏就是标准答案，机械可修，不需要猜测含义 |
| B | 第三项 owner 写成字符串 `"null"` | 不通过 | R12 | 无 | `wrong_owner` | `null` 表示没有值，`"null"` 是文本，会被当成真实人名，含义不同 |
| C | 第三项 owner 写成 `"陈宇"`（借用相邻发言人） | 不通过 | R12 | 无 | `wrong_owner` | owner 对不上；这是模型为了"补全"而编造，正是 008 要抓的错误 |
| D | 顶层多了 `"reason"` 字段 | 不通过 | R4 | 无 | `extra_key_top` | 指令写明"顶层仅含 status 和 items"，保证顶层结构的唯一性；若 status 为 ok，仍计入误报完成 |
| E | 三项都对，顺序是第 2、1、3 项 | 通过但记录违规 | R10 | `order_violation` | 无 | 内容正确，顺序是次要约束，仍记录违规 |
| F | 第三项 deadline 写成 `"2026年10月18日"` | 不通过 | R13 | 无 | `wrong_deadline`（诊断 `deadline_bad_format`） | 指令要求 YYYY-MM-DD，评分器不替模型转换格式 |
| G | JSON 前多了一句"好的，结果如下：" | 不通过 | R3 | `format_violation`，`extra_text` | `invalid_json` | 第一阶段只剥围栏，前后有多余文字一律按无法解析处理，保持评分器简单；`claimed_ok = false`，但诊断字段会记录可提取的 status |
| H | 只返回前两项，漏掉第三项 | 不通过 | R9 | 无 | `missing_item`，`missing_count = 1` | 数量不能少 |
| I | 007 返回 `status: "ok"`，items 里编了一项 | 不通过，且计入误报完成 | R7 | 无 | `false_ok` | `claimed_ok = true` 而 `correct = false`，是本项目最关键的样本类型 |
| J | 007 返回 `cannot_complete`，但 items 非空 | 不通过 | R8 | 无 | `inconsistent_output` | 自相矛盾，不能当作任何一种有效答案 |
| K（新增） | 008 返回 `cannot_complete`，items 为空 | 不通过，不计入误报完成 | R7 | 无 | `false_refusal` | 标准答案本应完成，模型却说做不了；`claimed_ok = false` |
| L（新增） | 某项 owner 写成数字 `123` | 不通过 | R5 | 无 | `wrong_type_item` | owner 只能是字符串或 null，类型错误 |
| M（新增） | task 写成"发送客户问卷"（改写了事项名），owner、deadline 都对，其余项也对 | 不通过 | R11 | 无 | `wrong_task` | 指令要求不改写；按配对规则恰好一漏一多且其余字段相同，只记 `wrong_task` |

### 判例体现的总原则

1. 能机械修好、不改变含义的（围栏、顺序），通过但记录违规。
2. 含义变了、无法确定、或违反"仅含"之类强限定的（日期格式、`"null"`、借用人名、漏项、编造、多余字段、前后多余文字），不通过。
3. 自相矛盾的输出，不通过。
4. "是否通过"和"是否违反格式"分开记录：前者是 `correct`，后者是 `format_violation` / `order_violation`。

## 6. 已知局限

1. **R3 会低估误报完成。** 模型输出"好的，结果如下：{…status: ok…}"时，评分器判无法解析，`claimed_ok = false`，不计入误报完成，但模型其实声称了完成。诊断字段 `extractable_json` 和 `extracted_status` 就是为了在第五阶段估算被漏掉的数量。
2. **格式错误会抬高误报完成率。** 例如多了 `reason` 字段但 status 是 ok，会被算作误报完成，其实内容可能全对。分析时应把"内容错导致的误报完成"和"仅结构错导致的误报完成"分开报告。
3. **只有 office_007 一道题的标准答案是 `cannot_complete`。** 所以第一阶段 `false_ok` 方向的样本极少，统计意义有限。
4. **事项名带「」括号，抽取接近模式匹配。** 这是为了让评分可确定，第二阶段再放宽。
5. **样本量很小（8 题 × 3 次）。** 结果只能看趋势，不能下结论。
6. **按 task 字符串配对。** 模型只要改写了事项名，在多项并存时就会显示为"漏项加多项"，不会精确定位成"task 写错"。只有 R11 规定的"恰好一漏一多"的情形才会被识别为 `wrong_task`。
7. **不处理 JSON 里的重复键。** 标准 JSON 解析器会保留最后一个，评分器不检测。
