#!/bin/zsh

set -eu

PROJECT_DIR="/Users/fifidei/Documents/Codex/liangshan-promotion-workbench"
SOURCE_PLIST="$PROJECT_DIR/scripts/com.fifidei.liangshan-workbench-refresh.plist"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$TARGET_DIR/com.fifidei.liangshan-workbench-refresh.plist"

mkdir -p "$TARGET_DIR" "$PROJECT_DIR/work"
cp "$SOURCE_PLIST" "$TARGET_PLIST"

launchctl bootout "gui/$UID" "$TARGET_PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID" "$TARGET_PLIST"
launchctl kickstart -k "gui/$UID/com.fifidei.liangshan-workbench-refresh"

echo "推广工作台本机刷新服务已启动。"
