# 通过 ECS2 frp 和 nginx 暴露本机 DSA 服务

## Goal

将本机 `daily_stock_analysis` Web/API 服务（当前监听宿主机 `8001`）通过本机 frpc 打洞到 ECS2 frps，再由 ECS2 nginx 通过公网 HTTPS 域名代理访问，并接入 ECS2 现有 SSL 自动续期机制。

用户要求本轮使用 grilling 方式先审视方案，再执行配置。

## Confirmed Facts

- 本机项目目录：`/home/zhangjianyong/project/daily_stock_analysis`。
- 本机 DSA 服务当前由 Docker 容器 `stock-server` 提供，容器健康状态为 healthy，宿主机端口映射为 `0.0.0.0:8001->8001/tcp`。
- 本机 `.env` 当前设置 `WEBUI_PORT=8001` / `API_PORT=8001`；8000 端口当前被其他项目占用。
- 本机 frpc 由用户级 systemd 服务 `~/.config/systemd/user/frpc.service` 管理，启动命令为 `~/.local/bin/frpc -c ~/.frpc/frpc.ini`。
- 本机 frpc 当前已有 `local-ssh-50022` 与 `ainovel` 代理；尚未配置 DSA 的 `8001` 代理。
- ECS2 上 frps 由 `frps.service` 管理，启动命令为 `/usr/local/bin/frps -c /etc/frp/frps.ini`。
- ECS2 frps 当前监听 `7000`、`7500`、`8080`、`8443`、`50022`，其中 `8080` 为 HTTP vhost，`8443` 为 HTTPS vhost。
- ECS2 nginx 实际运行二进制为 `/usr/local/nginx/sbin/nginx`，配置目录为 `/usr/local/nginx/conf/conf.d/`。
- ECS2 `stock.zhangjianyong.top` 当前由 `/usr/local/nginx/conf/conf.d/stock.conf` 管理，静态目录为 `/usr/share/nginx/stock`，`/api/` 反代到 `127.0.0.1:8081`；它不是当前本机 DSA 容器的入口。
- `https://stock.zhangjianyong.top/` 当前证书校验失败，表现为证书已过期；跳过证书校验时 nginx 仍能返回页面。
- ECS2 SSL 自动续期记录在 `/home/zhangjianyong/project/server_environment/docs/ecs2-environment.md`，远端目录为 `/root/ssl_auto_renew`，域名映射由 `/root/ssl_auto_renew/domains.conf` 维护。
- ECS2 `/root/ssl_auto_renew/domains.conf` 已包含 `stock.zhangjianyong.top:/usr/local/nginx/conf/conf.d/stock.conf`。
- ECS2 `/root/ssl_auto_renew/ssl_auto_renew.sh apply auto` 会遍历 `domains.conf` 中所有域名；本次证书处理只针对 `stock.zhangjianyong.top`，避免触碰其他域名。
- 本次最终链路已配置为 `stock.zhangjianyong.top` -> ECS2 nginx -> ECS2 frps HTTP vhost `127.0.0.1:8080` -> 本机 frpc `[dsa-stock]` -> 本机 DSA `127.0.0.1:8001`。
- `stock.zhangjianyong.top` 证书已切换为 Let's Encrypt，证书有效期为 2026-07-10 至 2026-10-08。

## Requirements

- 通过 frp 将本机 `127.0.0.1:8001` 或等价本机 DSA 入口暴露到 ECS2。
- 通过 ECS2 nginx 对公网提供 HTTPS 入口，域名使用 `stock.zhangjianyong.top`。
- 配置 SSL 证书，并纳入 ECS2 现有自动续期流程。
- 公网访问控制只依赖 DSA 自身登录鉴权；不额外增加 nginx Basic Auth 或 IP 白名单。
- 本次证书签发/更新只处理 `stock.zhangjianyong.top`；后续自动续期复用 ECS2 现有 `/root/ssl_auto_renew` cron 和 `domains.conf` 映射。
- 不泄露 frp token、证书私钥、API key、登录密码等敏感信息到仓库。
- 尽量避免影响 ECS2 上现有域名、现有 nginx 配置和现有 frps 代理。
- 允许备份并替换 ECS2 现有 `/usr/local/nginx/conf/conf.d/stock.conf`；旧静态页面不再作为 `stock.zhangjianyong.top` 公网入口。
- 保留明确回滚路径：删除或禁用新增 frpc 代理、删除或恢复 nginx 配置、移除证书自动续期映射、reload 服务。

## Acceptance Criteria

- [x] 本机 frpc 服务重载后，新增 DSA 代理启动成功且不影响已有 `local-ssh-50022`、`ainovel` 代理。
- [x] ECS2 frps 能收到 DSA 代理注册。
- [x] ECS2 nginx 配置语法检查通过。
- [x] 公网 HTTPS 域名能访问本机 DSA Web 页面。
- [x] 公网域名下 DSA API 路径可用。
- [x] HTTPS 证书有效，普通 `curl` 不需要 `-k` 即可通过证书校验。
- [x] 证书续期配置已纳入 ECS2 现有自动续期机制，且有可复查的配置入口。
- [x] 文档或 `AGENTS.md` 中记录不含敏感信息的最终入口、配置路径和运维命令。
