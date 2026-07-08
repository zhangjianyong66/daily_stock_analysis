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
  HTTP_PROXY/HTTPS_PROXY    构建阶段访问外网使用的代理；本地 127.0.0.1 代理会自动启用 host build network
  DOCKER_BUILD_HTTP_PROXY   覆盖传入 Docker build 的 HTTP 代理；本地代理默认不传 HTTP，避免 apt 走代理被拒绝
  DOCKER_BUILD_HTTPS_PROXY  覆盖传入 Docker build 的 HTTPS 代理
  DOCKER_BUILD_NETWORK      覆盖 Docker build 网络模式，默认按代理情况自动选择 default 或 host
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

has_local_proxy() {
  local proxy
  for proxy in "${HTTP_PROXY:-}" "${HTTPS_PROXY:-}" "${http_proxy:-}" "${https_proxy:-}"; do
    case "$proxy" in
      http://127.0.0.1:*|https://127.0.0.1:*|http://localhost:*|https://localhost:*|http://[::1]:*|https://[::1]:*)
        return 0
        ;;
    esac
  done

  return 1
}

prepare_build_env() {
  if [[ -z "${HTTP_PROXY:-}" && -n "${http_proxy:-}" ]]; then
    export HTTP_PROXY="$http_proxy"
  fi
  if [[ -z "${HTTPS_PROXY:-}" && -n "${https_proxy:-}" ]]; then
    export HTTPS_PROXY="$https_proxy"
  fi
  if [[ -z "${NO_PROXY:-}" && -n "${no_proxy:-}" ]]; then
    export NO_PROXY="$no_proxy"
  fi
  if [[ -z "${http_proxy:-}" && -n "${HTTP_PROXY:-}" ]]; then
    export http_proxy="$HTTP_PROXY"
  fi
  if [[ -z "${https_proxy:-}" && -n "${HTTPS_PROXY:-}" ]]; then
    export https_proxy="$HTTPS_PROXY"
  fi
  if [[ -z "${no_proxy:-}" && -n "${NO_PROXY:-}" ]]; then
    export no_proxy="$NO_PROXY"
  fi

  if [[ -z "${DOCKER_BUILD_NETWORK:-}" ]]; then
    if has_local_proxy; then
      export DOCKER_BUILD_NETWORK=host
      info "检测到本机代理，Docker 构建阶段使用 host 网络以访问 ${HTTPS_PROXY:-${HTTP_PROXY:-local proxy}}"
    else
      export DOCKER_BUILD_NETWORK=default
    fi
  fi

  if [[ -z "${DOCKER_BUILD_HTTPS_PROXY+x}" ]]; then
    export DOCKER_BUILD_HTTPS_PROXY="${HTTPS_PROXY:-}"
  fi
  if [[ -z "${DOCKER_BUILD_https_proxy+x}" ]]; then
    export DOCKER_BUILD_https_proxy="${https_proxy:-${DOCKER_BUILD_HTTPS_PROXY:-}}"
  fi
  if [[ -z "${DOCKER_BUILD_NO_PROXY+x}" ]]; then
    export DOCKER_BUILD_NO_PROXY="${NO_PROXY:-}"
  fi
  if [[ -z "${DOCKER_BUILD_no_proxy+x}" ]]; then
    export DOCKER_BUILD_no_proxy="${no_proxy:-${DOCKER_BUILD_NO_PROXY:-}}"
  fi

  if [[ -z "${DOCKER_BUILD_HTTP_PROXY+x}" ]]; then
    if has_local_proxy; then
      export DOCKER_BUILD_HTTP_PROXY=""
    else
      export DOCKER_BUILD_HTTP_PROXY="${HTTP_PROXY:-}"
    fi
  fi
  if [[ -z "${DOCKER_BUILD_http_proxy+x}" ]]; then
    if has_local_proxy; then
      export DOCKER_BUILD_http_proxy=""
    else
      export DOCKER_BUILD_http_proxy="${http_proxy:-${DOCKER_BUILD_HTTP_PROXY:-}}"
    fi
  fi
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
  prepare_build_env

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
