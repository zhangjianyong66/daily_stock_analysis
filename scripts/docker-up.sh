#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.yml"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
ENV_EXAMPLE="$ROOT_DIR/.env.example"
ACTION="${1:-build-up}"
TARGET="${2:-server}"

usage() {
  cat <<'EOF'
用法:
  scripts/docker-up.sh [操作] [目标]

操作:
  build-up        构建并启动目标服务（默认）
  up | start      启动目标服务，不重新构建
  build           只构建目标服务
  restart         构建并强制重建启动目标服务
  stop            停止目标服务
  down            停止并删除整个 compose stack
  ps | status     查看服务状态
  logs            跟随查看目标服务日志
  help            显示帮助

目标:
  server          WebUI + FastAPI 服务（默认）
  analyzer        定时分析服务
  all             server + analyzer

示例:
  scripts/docker-up.sh
  scripts/docker-up.sh up
  scripts/docker-up.sh restart
  scripts/docker-up.sh restart analyzer
  scripts/docker-up.sh up all
  scripts/docker-up.sh stop server
  scripts/docker-up.sh down
  scripts/docker-up.sh logs

环境变量:
  ENV_FILE=/path/to/.env   指定 Docker Compose 使用的 env 文件，默认项目根目录 .env
EOF
}

die() {
  echo "错误: $*" >&2
  exit 1
}

info() {
  echo "==> $*"
}

ensure_env_file() {
  if [[ -f "$ENV_FILE" ]]; then
    return
  fi

  [[ -f "$ENV_EXAMPLE" ]] || die "找不到配置模板: $ENV_EXAMPLE"
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  info "已从 .env.example 创建 $ENV_FILE，请按需补充 API Key、STOCK_LIST 和通知配置。"
}

docker_cmd() {
  if docker ps >/dev/null 2>&1; then
    printf 'docker'
    return
  fi

  if command -v sudo >/dev/null 2>&1 && sudo -n docker ps >/dev/null 2>&1; then
    printf 'sudo -n docker'
    return
  fi

  die "当前用户无法访问 Docker。请启动 Docker，或把当前用户加入 docker 组。"
}

compose_cmd() {
  local docker_bin="$1"

  if $docker_bin compose version >/dev/null 2>&1; then
    printf '%s compose' "$docker_bin"
    return
  fi

  if command -v docker-compose >/dev/null 2>&1 && docker-compose version >/dev/null 2>&1; then
    printf 'docker-compose'
    return
  fi

  die "Docker Compose 不可用。请安装 Docker Compose 插件或 docker-compose。"
}

resolve_services() {
  case "$TARGET" in
    server)
      printf 'server'
      ;;
    analyzer)
      printf 'analyzer'
      ;;
    all)
      printf 'server analyzer'
      ;;
    *)
      die "未知目标: $TARGET。可用目标: server、analyzer、all"
      ;;
  esac
}

run_compose() {
  local compose="$1"
  shift

  $compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

main() {
  case "$ACTION" in
    -h|--help|help)
      usage
      return
      ;;
  esac

  cd "$ROOT_DIR"
  ensure_env_file

  local docker_bin compose services
  docker_bin="$(docker_cmd)"
  compose="$(compose_cmd "$docker_bin")"
  services="$(resolve_services)"

  case "$ACTION" in
    build-up)
      info "构建服务: $services"
      run_compose "$compose" build $services
      info "启动服务: $services"
      run_compose "$compose" up -d $services
      run_compose "$compose" ps
      ;;
    up|start)
      info "启动服务: $services"
      run_compose "$compose" up -d $services
      run_compose "$compose" ps
      ;;
    build)
      info "构建服务: $services"
      run_compose "$compose" build $services
      ;;
    restart)
      info "构建服务: $services"
      run_compose "$compose" build $services
      info "强制重建并启动服务: $services"
      run_compose "$compose" up -d --force-recreate $services
      run_compose "$compose" ps
      ;;
    stop)
      info "停止服务: $services"
      run_compose "$compose" stop $services
      run_compose "$compose" ps
      ;;
    down)
      info "停止并删除 compose stack"
      run_compose "$compose" down
      ;;
    ps|status)
      run_compose "$compose" ps
      ;;
    logs)
      run_compose "$compose" logs -f $services
      ;;
    *)
      usage
      die "未知操作: $ACTION"
      ;;
  esac
}

main "$@"
