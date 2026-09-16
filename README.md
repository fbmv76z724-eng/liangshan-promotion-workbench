# 推广工作台

移动端优先的静态推广数据工作台。访问者无需登录，页面只读取最近一次由 Codex 同步生成的快照。

## 本地运行

```bash
python3 -m http.server 4173 -d docs
```

浏览器打开 `http://127.0.0.1:4173/`。

## 更新数据

默认自动寻找最近一次成功完成的每日推广导出：

```bash
python3 scripts/sync_snapshot.py
```

也可以明确指定导出目录和当月推广数据：

```bash
python3 scripts/sync_snapshot.py \
  --daily-dir /path/to/tongbao-YYYYMMDD \
  --promo /path/to/X月推广数据.xlsx
```

生成结果写入 `docs/data/snapshot.json`。脚本会在写入前校验 12 个队伍、人员工号、订单日期，并与最新 `bt5_*.tsv` 对账。

更新今日推广状态：

```bash
python3 scripts/sync_today.py
```

脚本通过 ego-lite 直接读取钉钉推广网页，只保留本月真实转单不足 2 单的司机，按“姓名 + 队伍”匹配今日已完成状态，并生成 `docs/data/today.json`。今日已完成司机默认排在前面。推广日按当天 06:00 至次日 06:00 计算；状态未变化时不会重写快照。页面每 5 分钟重新读取一次，并显示数据更新时间和页面刷新时间；读取失败时继续显示上一次成功数据。

定时任务使用单入口脚本完成同步、测试、发布、Pages 构建等待和线上校验：

```bash
/Users/fifidei/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  scripts/run_workbench.py
```

脚本只在数据变化时发布。发布中断会记录待发布状态，并在后续运行中继续；同一故障只提示一次，恢复时再提示。

发布到 GitHub Pages：

```bash
python3 scripts/publish_github.py
```

当前网络如果无法直接使用 `git push`，该脚本会通过已登录的 GitHub CLI API 创建提交并更新 `main` 分支。

## 测试

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
sh scripts/test_logic.sh
```

## 数据口径

- 统计周期为当月 1 日至最近一次成功同步日。
- 出车天数按个人台账中该工号当月出现的日期数计算。
- 推广次数为当月推广提交次数。
- 推广差值为当月推广提交次数减个人台账累计“否”次数，允许负数。
- 真实转单沿用现有推广数据口径，并排除命中作弊单的记录。
- 本月推广是否完成按扣作弊后的真实转单数是否达到 2 单判断。
- 工单查询按“推荐司机工号”精确匹配，返回全部匹配订单，不额外筛选真实推广。

## 公开范围

页面包含 `noindex,nofollow` 和 `robots.txt`，但这只能阻止搜索引擎收录。GitHub Pages 与公开仓库中的数据仍可被拿到链接或访问仓库的人直接获取。
