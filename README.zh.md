# seedlot

**多种子 RL 结果聚合闸门。** 把每个种子的运行日志交给它，它计算 n、均值 ± 样本标准差、IQR、中位数和 95% 置信区间，并在结论不被支持时 fail-closed。硬 FAIL（退出码 3）：单一种子，或两臂 CI 重叠。WARN（退出码 2）：少于 3 个种子、零方差、重复标签/词干——声称稳定前需先检查，但不是硬阻断。

纯 Python 标准库。不联网，不依赖 torch/numpy/scipy，无需 C 编译。Windows / macOS / Linux，Python 3.10+。

## 解决什么问题

RL 结果对种子敏感，但 agent 和研究者常拿一条幸运曲线写标题均值，或把两条重叠分布称为"更优"。审稿人反复用"只有一个种子""没有分布"驳回。seedlot 把你已有的日志变成分布摘要，在不被支持的措辞进入草稿之前拦下它。

它**不**训练任何东西，**不**做正式假设检验，也**不**能挽救一个薄弱实验——它只报告数字允许你说什么。

## 安装

无需编译，无需安装依赖。

- **Claude Code（通过 GitHub 个人市场）：**

  ```bash
  claude plugin marketplace add dafahaha/seedlot
  claude plugin install seedlot@seedlot
  ```

  在会话内等价于先 `/plugin marketplace add dafahaha/seedlot`，再
  `/plugin install seedlot@seedlot`。

- **Claude Code（本地开发）：** `claude --plugin-dir ./seedlot`。

- **便携 skill（Codex CLI / Cursor / Gemini CLI / Roo Code）：** 把
  `skills/seedlot/` 复制到客户端的 skills 目录（`~/.codex/skills/`、
  `.agents/skills/` 等）。这些客户端只要求 `name`/`description` frontmatter，
  额外字段会被忽略。

## 用法

目录模式——每个 CSV 一个种子，自动识别奖励列：

```bash
python skills/seedlot/scripts/seedlot.py ./runs --arm-name my-method
```

两臂对比：

```bash
python skills/seedlot/scripts/seedlot.py ./runs/method \
  --compare ./runs/baseline --compare-name baseline \
  --reward-column eval_return --json
```

单 CSV 带种子列，每个种子取最后 5 个 episode 的均值：

```bash
python skills/seedlot/scripts/seedlot.py all_runs.csv \
  --seed-column seed --last-k 5 --output report.md
```

### 输入格式

- 目录模式：每个 `.csv` 是一个种子；奖励列最后一行 = 该种子取值。
- 单 CSV：`--seed-column` 分组；`--reward-column` 指定指标列。
- 自动识别的奖励列名：`reward`、`eval_return`、`return`、
  `episode_return`、`mean_return`、`score`。

### 退出码

| 码 | 含义 |
|---|---|
| 0 | 干净摘要，无警告 |
| 2 | 有警告（n<3、零方差、重复标签等） |
| 3 | 硬闸门失败（单一种子、CI 重叠） |
| 1 | 用法 / IO 错误（缺文件、空目录、不可读/格式错误、无数据） |

## 输出

默认 Markdown；`--json` 输出结构化载荷（摘要、对比、失败、警告）供 CI 闸门使用。
Markdown 的 `## gates` 段落逐条列出 FAIL/WARN 的行级原因。

## 相关工作

- [rliable](https://github.com/google-research/rliable)（arXiv:2108.13264）是论文级基准统计库：分层 bootstrap CI、IQM、性能剖面、改进概率，依赖 numpy/scipy，输入是 `(runs × tasks)` 矩阵。seedlot 不替代它；本工具是零安装、写作前的闸门，处理你已有的逐种子日志，带退出码供 CI 使用，不做正式推断。
- Stable-Baselines3 的 `evaluate_policy` 对同一策略跑 N 个评估 episode 取均值；它度量的是评估离散度，不是本工具汇总的跨训练种子分布。

## 测试

```bash
python -m pytest tests/ -q
```

53 个测试，仅标准库。人工谓词变异抽查（翻转 CI 重叠谓词会使重叠测试变红；记录在 CHANGELOG）。

## 限制（诚实披露）

- 仅描述性统计——不做正式假设检验、bootstrap 或贝叶斯区间；小 n 的宽 CI 刻意保留宽度。*不重叠*的 95% CI 是数值闸门，不是优越性证明；*重叠*的 CI 是保守的"不支持优越性"启发式，不等于证明两臂等价。
- t 临界值在 df=30 以内为精确值；df>30 使用 Cornish-Fisher t 近似（相对 scipy 误差 <5e-4，随 df 增大收敛到 1.96 正态尾），报告中标注 `t-approx`，不会因硬 1.96 而把 CI 收窄。
- 信任种子标签：无法识别两个标签不同的种子实际用了相同初始化。
- CSV 全量读入内存：请指向本地日志，不要喂多 GB 转储。
- 不记录环境/库版本，请另存清单。
- 不是论文写作助手；只核对数字与结论是否相符。

## 许可证

MIT，© 2026 Daizhi Liao (dafahaha)。
