#!/bin/bash
# Mac：雙擊打開教授研究檔案（看資料時保持這個視窗開著；關掉視窗會同步到雲端並結束）
cd "$(dirname "$0")" || exit 1
UV=$(command -v uv || ls "$HOME/.local/bin/uv" 2>/dev/null)
if [ -z "$UV" ]; then
  echo "找不到 uv。請先在「終端機」執行：curl -LsSf https://astral.sh/uv/install.sh | sh ，裝好後再雙擊一次。"
  read -n1 -r -p "按任意鍵關閉"; exit 1
fi
"$UV" sync -q && exec "$UV" run python scripts/app.py --window "$@"
read -n1 -r -p "啟動失敗，按任意鍵關閉"
