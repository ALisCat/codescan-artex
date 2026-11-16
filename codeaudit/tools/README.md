# 矩阵生成器（v1.2）

```bash
python3 cellgen.py <源码目录> <输出目录> [--low]
```

输出：

- `cells.json` 全矩阵（applicable / needs_review / not_applicable / unverified）
- `tasks.json` 要派发的格子（含三段式任务书、结构化 hints）
- `review.json` 低置信格子清单（`dispatched` 标记是否派单）
- `report.json` 汇总指标

可选参数：

- `--low` 低置信格子也派单（默认只保留在矩阵里，不消耗 token）

导入平台：

```bash
python3 mkfull.py <输出目录>/cells.json <输出目录>/tasks.json import.json
# POST /api/codeaudit/tasks/{id}/import  body = import.json
```

demo 评测（ground truth）：

```bash
python3 demo_eval.py <输出目录> <demo目录>/GROUND-TRUTH.csv
```

验收：

```bash
python3 acceptance.py <输出目录>/tasks.json <源码目录> [预算=120]
```

设计说明见 `../MATRIX-DESIGN.md` 第 24 节。
