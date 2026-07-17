#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.yml"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
ENV_EXAMPLE="$ROOT_DIR/.env.example"
ACTION="${1:-build-up}"
TARGET="${2:-server}"
DEFAULT_DOCKER_BUILD_PROXY="http://127.0.0.1:10808"
DEFAULT_DEBIAN_APT_MIRROR="https://mirrors.tuna.tsinghua.edu.cn/debian"
DEFAULT_DEBIAN_SECURITY_APT_MIRROR="https://mirrors.tuna.tsinghua.edu.cn/debian-security"
COMPOSE_PROFILE_ARGS=()
STARTUP_SERVICES=""

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
  HTTP_PROXY/HTTPS_PROXY    可作为运行环境代理输入；Docker build 默认使用 127.0.0.1:10808
  DOCKER_BUILD_HTTP_PROXY   覆盖传入 Docker build 的 HTTP 代理；本地代理默认不传 HTTP，避免 apt 走代理被拒绝
  DOCKER_BUILD_HTTPS_PROXY  覆盖传入 Docker build 的 HTTPS 代理，默认 http://127.0.0.1:10808
  DOCKER_BUILD_NETWORK      覆盖 Docker build 网络模式，默认 host
  DEBIAN_APT_MIRROR         覆盖 Docker build 阶段 Debian 主源，默认清华 HTTPS 镜像
  DEBIAN_SECURITY_APT_MIRROR 覆盖 Docker build 阶段 Debian security 源，默认清华 HTTPS 镜像

服务联动:
  当 ENV_FILE 中 SEARCH_ROUTING_MODE=searxng_first_cn 时，build-up、up/start、restart
  会自动启用 searxng profile，并在目标服务之外同时启动私有 SearXNG。
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

read_env_value() {
  local key="$1" value

  value="$(
    awk -v key="$key" '
      {
        line = $0
        sub(/^[[:space:]]+/, "", line)
        sub(/^export[[:space:]]+/, "", line)
        separator = index(line, "=")
        if (separator == 0) {
          next
        }
        candidate = substr(line, 1, separator - 1)
        sub(/[[:space:]]+$/, "", candidate)
        if (candidate == key) {
          value = substr(line, separator + 1)
        }
      }
      END { print value }
    ' "$ENV_FILE"
  )"

  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  case "$value" in
    \"*\")
      value="${value#\"}"
      value="${value%\"}"
      ;;
    \'*\')
      value="${value#\'}"
      value="${value%\'}"
      ;;
    *)
      value="${value%%[[:space:]]#*}"
      value="${value%"${value##*[![:space:]]}"}"
      ;;
  esac

  printf '%s' "$value"
}

configure_optional_services() {
  local services="$1"
  local routing_mode

  COMPOSE_PROFILE_ARGS=()
  STARTUP_SERVICES="$services"
  routing_mode="$(read_env_value SEARCH_ROUTING_MODE)"

  if [[ "$routing_mode" != "searxng_first_cn" ]]; then
    return
  fi

  COMPOSE_PROFILE_ARGS=(--profile searxng)
  case "$ACTION" in
    build-up|up|start|restart)
      STARTUP_SERVICES="$services searxng"
      info "检测到 SEARCH_ROUTING_MODE=searxng_first_cn，将同时启动私有 SearXNG"
      ;;
  esac
}

run_compose() {
  local compose="$1"
  shift

  $compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "${COMPOSE_PROFILE_ARGS[@]}" "$@"
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
    export DOCKER_BUILD_NETWORK=host
  fi

  if [[ -z "${DOCKER_BUILD_HTTPS_PROXY+x}" ]]; then
    export DOCKER_BUILD_HTTPS_PROXY="$DEFAULT_DOCKER_BUILD_PROXY"
  fi
  if [[ -z "${DOCKER_BUILD_https_proxy+x}" ]]; then
    export DOCKER_BUILD_https_proxy="$DOCKER_BUILD_HTTPS_PROXY"
  fi
  if [[ -z "${DOCKER_BUILD_NO_PROXY+x}" ]]; then
    export DOCKER_BUILD_NO_PROXY="${NO_PROXY:-}"
  fi
  if [[ -z "${DOCKER_BUILD_no_proxy+x}" ]]; then
    export DOCKER_BUILD_no_proxy="${no_proxy:-${DOCKER_BUILD_NO_PROXY:-}}"
  fi

  if [[ -z "${DOCKER_BUILD_HTTP_PROXY+x}" ]]; then
    export DOCKER_BUILD_HTTP_PROXY=""
  fi
  if [[ -z "${DOCKER_BUILD_http_proxy+x}" ]]; then
    export DOCKER_BUILD_http_proxy=""
  fi

  if [[ -z "${DEBIAN_APT_MIRROR:-}" ]]; then
    export DEBIAN_APT_MIRROR="$DEFAULT_DEBIAN_APT_MIRROR"
  fi
  if [[ -z "${DEBIAN_SECURITY_APT_MIRROR:-}" ]]; then
    export DEBIAN_SECURITY_APT_MIRROR="$DEFAULT_DEBIAN_SECURITY_APT_MIRROR"
  fi

  info "Docker 构建阶段使用网络: $DOCKER_BUILD_NETWORK"
  info "Docker 构建阶段 HTTPS 代理: ${DOCKER_BUILD_HTTPS_PROXY:-未设置}"
  info "Docker 构建阶段 Debian 源: $DEBIAN_APT_MIRROR"
  info "Docker 构建阶段 Debian security 源: $DEBIAN_SECURITY_APT_MIRROR"
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
  configure_optional_services "$services"
  prepare_build_env

  case "$ACTION" in
    build-up)
      info "构建服务: $services"
      run_compose "$compose" build $services
      info "启动服务: $STARTUP_SERVICES"
      run_compose "$compose" up -d $STARTUP_SERVICES
      run_compose "$compose" ps
      ;;
    up|start)
      info "启动服务: $STARTUP_SERVICES"
      run_compose "$compose" up -d $STARTUP_SERVICES
      run_compose "$compose" ps
      ;;
    build)
      info "构建服务: $services"
      run_compose "$compose" build $services
      ;;
    restart)
      info "构建服务: $services"
      run_compose "$compose" build $services
      info "强制重建并启动服务: $STARTUP_SERVICES"
      run_compose "$compose" up -d --force-recreate $STARTUP_SERVICES
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
