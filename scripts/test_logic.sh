#!/bin/sh
set -eu

if command -v node >/dev/null 2>&1; then
  node --test tests/logic.test.mjs
  exit 0
fi

bundled_node="${CODEX_NODE_BIN:-$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node}"
if [ -x "$bundled_node" ]; then
  "$bundled_node" --test tests/logic.test.mjs
  exit 0
fi

echo "未找到 Node.js，无法运行前端逻辑测试。" >&2
exit 1
