#!/usr/bin/env bash
# OpenHub 一次性安装脚本
# 用法：sudo bash deploy/install.sh [--mode docker|bare] [--dir /opt/openhub]
# 目标：一条命令完成 环境检测 → 拉起服务 → 初始化管理员 → 生成 API Key
set -euo pipefail

MODE="docker"
INSTALL_DIR="/opt/openhub"
while [ $# -gt 0 ]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --dir)  INSTALL_DIR="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

echo "== OpenHub 安装 =="
echo "模式: $MODE | 目录: $INSTALL_DIR"

gen_secret() { python3 -c 'import secrets;print(secrets.token_urlsafe(32))'; }

# 1) 环境检测
command -v python3 >/dev/null || { echo "需要 Python 3"; exit 1; }
PY_VER=$(python3 -c 'import sys;print(sys.version_info.minor)')
[ "$PY_VER" -ge 10 ] || { echo "需要 Python 3.10+"; exit 1; }

# 2) 生成凭据（.env，权限 600）
mkdir -p "$INSTALL_DIR/deploy" "$INSTALL_DIR/data"
ENV_FILE="$INSTALL_DIR/deploy/.env"
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<EOF
OPENHUB_ADMIN_TOKEN=$(gen_secret)
OPENHUB_INITIAL_API_KEY=ohk_$(gen_secret)
OPENHUB_PORT=8080
OPENHUB_ENABLED_PLUGINS=cardkey,update,crash
EOF
  chmod 600 "$ENV_FILE"
  echo "已生成凭据: $ENV_FILE (权限 600)"
else
  echo "凭据文件已存在，跳过生成: $ENV_FILE"
fi

# 3) 按模式拉起
if [ "$MODE" = "docker" ]; then
  command -v docker >/dev/null || { echo "未检测到 docker，请改用 --mode bare"; exit 1; }
  (cd "$INSTALL_DIR" && docker compose -f deploy/docker-compose.yml up -d --build)
  echo "Docker 模式已启动"
elif [ "$MODE" = "bare" ]; then
  python3 -m venv "$INSTALL_DIR/.venv"
  "$INSTALL_DIR/.venv/bin/pip" install -q --upgrade pip
  "$INSTALL_DIR/.venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"
  if command -v systemctl >/dev/null; then
    cp "$INSTALL_DIR/deploy/openhub.service.example" /etc/systemd/system/openhub.service
    systemctl daemon-reload && systemctl enable --now openhub
    echo "systemd 服务已启用"
  else
    echo "无 systemd，请手动运行："
    echo "  $INSTALL_DIR/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8080"
  fi
else
  echo "未知模式: $MODE"; exit 1
fi

echo "== 完成 =="
echo "管理后台: http://<服务器IP>:8080/"
echo "API 文档: http://<服务器IP>:8080/docs"
echo "管理员 Token 与初始 API Key 见 $ENV_FILE（请妥善保管，不要提交到仓库）"
