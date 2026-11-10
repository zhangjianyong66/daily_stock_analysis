# 本机与 ECS2 运维线索

## 来源与时效

2026-11-09 从 AGENTS.md 的“本机 / ECS2 当前部署备注”迁入；下列内容是旧文档记录，迁移时未查询真实 .env、容器、远程服务或证书状态。端口、路径、代理和域名必须在操作前重新核实，不能据此直接重启服务或执行管理员操作。

外部运维记录入口：`/home/zhangjianyong/project/server_environment/docs/ecs2-environment.md`；此处只保留本项目转发链路的历史线索，不替代该文档。

## 历史记录（未重新验证）

- 本机 Docker 中 `daily-stock-analysis` 的 Web/API 服务通常由 `stock-server` 容器提供，启动命令为 `python main.py --serve-only --host 0.0.0.0 --port ${WEBUI_PORT:-${API_PORT:-8000}}`。
- 本机 Docker daemon 的 systemd 代理配置位于 `/etc/systemd/system/docker.service.d/http-proxy.conf`，当时使用 `http://127.0.0.1:7890`。Dockerfile 顶部 `# syntax=docker/dockerfile:1.7` 和基础镜像元数据由 daemon 拉取，不受 Compose `build.args` 或 `DOCKER_BUILD_HTTPS_PROXY` 控制；若此阶段出现 Docker Hub TLS 握手超时，应先验证 daemon 代理，修改后执行 `sudo systemctl daemon-reload && sudo systemctl restart docker`。
- 当时本机 8000 端口可能被其他项目占用；如 `.env` 中设置 `WEBUI_PORT=8001` / `API_PORT=8001`，`stock-server` 会映射为宿主机 `0.0.0.0:8001->8001/tcp`。
- 本机 frpc 由用户级 systemd 服务 `~/.config/systemd/user/frpc.service` 管理，配置入口为 `~/.frpc/frpc.ini`。该文件包含 frps token，禁止提交仓库。
- 当时本机 frpc 代理包含本机 SSH、其他项目域名以及本项目 `[dsa-stock]`。`[dsa-stock]` 使用 `type = http`、`local_ip = 127.0.0.1`、`local_port = 8001`、`custom_domains = stock.zhangjianyong.top`，通过 ECS2 frps HTTP vhost 暴露 DSA。
- ECS2 的历史/运维记录在 `/home/zhangjianyong/project/server_environment/docs/ecs2-environment.md`；ECS2 nginx 常用配置目录为 `/usr/local/nginx/conf/conf.d/`，frps 配置为 `/etc/frp/frps.ini`。
- ECS2 上 `stock.zhangjianyong.top` 当时由 nginx `/usr/local/nginx/conf/conf.d/stock.conf` 管理，HTTPS 入口反代到 ECS2 frps HTTP vhost `http://127.0.0.1:8080`，再由本机 frpc `[dsa-stock]` 转发到本机 DSA `127.0.0.1:8001`。
- `stock.zhangjianyong.top` 证书使用 Let's Encrypt，nginx 证书路径为 `/usr/local/nginx/conf/cert/stock.zhangjianyong.top.pem` 和 `/usr/local/nginx/conf/cert/stock.zhangjianyong.top.key`；ECS2 `/root/ssl_auto_renew/domains.conf` 已包含该域名映射，root crontab 继续执行 `/root/ssl_auto_renew/ssl_auto_renew.sh apply auto` 与 `check`。

## 搜索配置历史

- 原记录称批次 `searxng-retirement-20260717` 隔离 206 条 SearXNG news_intel；迁移时未查询数据库确认。按批次回滚入口为 `scripts/quarantine_searxng_news_intel.py rollback --batch searxng-retirement-20260717`，执行前核实目标和授权，`search_api_calls` 永久保留。

原 AGENTS.md 曾记录：本机关闭公共 SearXNG、尚未配置 ANSPIRE_API_KEYS。此状态未重新验证，不作为现状或长期约束。排查只确认配置是否存在，不输出真实 Key。
