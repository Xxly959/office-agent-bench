# 第一阶段首次运行清单

- 进程开始时间（Asia/Shanghai）：2026-10-13T20:43:55.368834+08:00
- 进程结束时间（Asia/Shanghai）：2026-10-13T20:44:54.962138+08:00
- Inspect 日志开始时间（Asia/Shanghai）：2026-10-13T20:43:57+08:00
- Inspect 日志结束时间（Asia/Shanghai）：2026-10-13T20:44:54+08:00
- 工作目录：/Users/x/office-agent-bench
- 模型名：deepseek/deepseek-flash
- Provider base URL：https://api.deepseek.com
- Inspect 版本：0.3.278
- 每题重复次数：3
- 运行前任务集 shasum：7e1c1edb039fa9d28894c747834196d64dfa29da797bfccec3e54c53117c7215
- 运行后任务集 shasum：7e1c1edb039fa9d28894c747834196d64dfa29da797bfccec3e54c53117c7215
- 导出时任务集 shasum：7e1c1edb039fa9d28894c747834196d64dfa29da797bfccec3e54c53117c7215
- 日志文件：results/logs/2026-10-13T12-43-57-00-00_office-bench_MvoRpVQKoEnCfdUebzPJ2H.eval
- 命令原始输出：results/run_stage1_output.txt
- 总 token 数（日志 model_usage.total_tokens 合计）：15119
- Inspect 日志耗时（秒）：57.000000
- 进程耗时（秒）：59.593090
- 日志样本次数：24

完整命令：

```sh
rtk proxy .venv/bin/inspect eval office_bench/task.py --model deepseek/deepseek-flash --model-base-url https://api.deepseek.com --epochs 3 --no-epochs-reducer --max-retries 0 --retry-on-error 0 --fail-on-error 0 --timeout 60 --max-connections 1 --max-samples 1 --log-dir results/logs --log-format eval --no-log-model-api --display plain
```
