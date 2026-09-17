#!/bin/zsh

set -u

export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT_DIR="/Users/fifidei/Documents/Codex/liangshan-promotion-workbench"
PYTHON="/Users/fifidei/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
WORKBENCH_URL="https://fbmv76z724-eng.github.io/liangshan-promotion-workbench/"

cd "$PROJECT_DIR" || exit 1

clear
echo "正在更新推广工作台数据..."
echo

if "$PYTHON" scripts/run_workbench.py --full; then
  echo
  echo "更新完成，正在打开网页..."
  open "$WORKBENCH_URL"
else
  echo
  echo "更新失败，请查看上方提示。"
fi

echo
read -r -k 1 "?按任意键关闭窗口..."
