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
- 推广差值为当月推广提交次数减个人台账累计“否”次数，允许负数。
- 真实转单数量沿用现有每日推广管线口径。
- 工单查询按“推荐司机工号”精确匹配，返回全部匹配订单，不额外筛选真实推广。

## 公开范围

页面包含 `noindex,nofollow` 和 `robots.txt`，但这只能阻止搜索引擎收录。GitHub Pages 与公开仓库中的数据仍可被拿到链接或访问仓库的人直接获取。
