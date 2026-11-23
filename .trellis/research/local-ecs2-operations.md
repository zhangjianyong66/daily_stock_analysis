# 本机与 ECS2 运维线索

## 来源与时效

2026-11-09 从 AGENTS.md 的“本机 / ECS2 当前部署备注”迁入；“历史记录”及“搜索配置历史”小节是旧文档记录，迁入时未查询真实 .env、容器、远程服务或证书状态。后续核验单独标注日期。端口、路径、代理和域名必须在操作前重新核实，不能据此直接重启服务或执行管理员操作。

外部运维记录入口：`/home/zhangjianyong/project/server_environment/docs/ecs2-environment.md`；此处只保留本项目转发链路的历史线索，不替代该文档。

## 本机 Docker 迁移为用户服务（2026-11-10 主机时间核验）

- 用户确认使用当前本地代码和用户级 systemd。此次部署基于本地 HEAD `3fc2de94`，服务为 `stock-server.service`，unit 位于 `~/.config/systemd/user/stock-server.service`；后续操作前仍须核实当前状态。
- unit 使用项目 `.venv/bin/python`（此次为 Python 3.12），在项目根目录运行 `main.py --serve-only --host 0.0.0.0 --port 8001`；应用通过 `ENV_FILE` 读取项目 `.env`，时区为 `Asia/Shanghai`，`WEBUI_AUTO_BUILD=false`，前端需在部署时预先构建。
- 已执行用户级 enable，核实 `Linger=yes`；使用 `systemctl --user status/restart stock-server.service` 管理，使用 `journalctl --user -u stock-server.service -f` 查看日志。未重启主机验证开机行为。
- 数据库、认证文件、日志和报告继续使用项目原目录；`~/.longbridge` 链接到项目 `longbridge_tokens`，复用原 Docker 挂载的 OAuth 缓存。此次未触发付费分析或通知，也未进行长桥在线认证验证。
- 原 `stock-server` 容器已停止，restart policy 改为 `no`，容器及镜像保留。不要再通过 Docker 启动脚本启动它，否则会与本地服务争用端口。
- 切换前配置、认证文件、OAuth 缓存、容器元数据和 SQLite backup API 生成的数据库备份位于 `~/.local/state/daily-stock-analysis/backups/20261110T052124Z/`，该目录含敏感信息，不得提交。SQLite 备份与迁移后数据库均通过 `quick_check`，35 张既有表的行数保持一致。
- 已验证健康检查、首页及引用的静态资源、现有签名登录会话、未认证 API 返回 401、历史报告/持仓账户/设置读取及同值设置保存；配置值未变。Web 通过 npm 10 的安装、lint 和 build，lint 有一条既有 Hook 依赖警告。
- 受控重启曾因服务器旧连接处于 `TIME_WAIT` 而触发 `main.py` 的端口探测失败：实测普通 bind 返回 EADDRINUSE，启用 SO_REUSEADDR 后可绑定。此次不修改业务代码；unit 设置 `StartLimitIntervalSec=0`、`Restart=on-failure`、`RestartSec=5`，等待连接释放后自动恢复健康，重启可能需要约一分钟。
- 回滚先停止并禁用用户服务，再恢复旧容器 `unless-stopped` 策略并启动。回滚到旧代码前检查数据库兼容性；如需恢复切换前备份，先保存切换后的数据库和新增写入，不直接覆盖正在使用的数据。

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
