# 通过 ECS2 frp 和 nginx 暴露本机 DSA 服务 - Design

## Architecture

目标链路：

```text
公网浏览器
  -> https://stock.zhangjianyong.top
  -> ECS2 nginx:443
  -> ECS2 frps HTTP vhost:127.0.0.1:8080
  -> 本机 frpc proxy:dsa-stock
  -> 本机 DSA Web/API:127.0.0.1:8001
```

## Boundaries

- 本机只修改 `~/.frpc/frpc.ini`，新增一个 HTTP proxy，不改 frps token 和已有代理。
- ECS2 只修改 `stock.zhangjianyong.top` 相关 nginx 配置和证书，不改其他域名。
- 不改 DSA 应用代码、数据库、Docker Compose 结构或 `.env` 端口语义。

## frp Design

- 使用 frp HTTP vhost 代理，而不是 TCP remote_port。
- 本机 `~/.frpc/frpc.ini` 新增：

```ini
[dsa-stock]
type = http
local_ip = 127.0.0.1
local_port = 8001
custom_domains = stock.zhangjianyong.top
```

- 选择 HTTP vhost 的原因：
  - ECS2 frps 已有 `vhost_http_port = 8080`。
  - nginx 可通过 `proxy_pass http://127.0.0.1:8080` 加 `Host: stock.zhangjianyong.top` 路由到对应 frpc proxy。
  - 不需要新增公网 TCP 端口或改阿里云安全组。

## nginx Design

- 备份 ECS2 现有 `/usr/local/nginx/conf/conf.d/stock.conf`。
- 替换为 HTTP 强制跳转 HTTPS + HTTPS 反代配置。
- 保留 `/.well-known/acme-challenge/` webroot，用于 HTTP-01 证书签发/续期。
- HTTPS `location /` 反代到 `http://127.0.0.1:8080`，并显式设置：
  - `Host $host`：让 frps 按 `custom_domains` 路由。
  - `X-Real-IP` / `X-Forwarded-For` / `X-Forwarded-Proto`：保留上游请求信息。
  - `Upgrade` / `Connection`：支持 WebSocket / SSE 类长连接。
  - 较长 `proxy_read_timeout` / `proxy_send_timeout`：避免长耗时分析接口被 nginx 过早断开。

## SSL Design

- 不运行 `/root/ssl_auto_renew/ssl_auto_renew.sh apply auto`，避免触碰所有域名。
- 本次只对 `stock.zhangjianyong.top` 执行单域名 certbot webroot 签发/续期。
- 证书文件使用 nginx 现有路径：
  - `/usr/local/nginx/conf/cert/stock.zhangjianyong.top.pem`
  - `/usr/local/nginx/conf/cert/stock.zhangjianyong.top.key`
- `/root/ssl_auto_renew/domains.conf` 已包含 `stock.zhangjianyong.top:/usr/local/nginx/conf/conf.d/stock.conf`，后续 cron 自动续期继续覆盖该域名。

## Compatibility

- `stock.zhangjianyong.top` 旧静态页面会被替换为当前 DSA Web/API。
- DSA 当前 `ADMIN_AUTH_ENABLED=true`，公网访问只依赖 DSA 自身登录鉴权，不加 nginx Basic Auth 或 IP 白名单。
- 本机 8001 端口继续由 Docker `stock-server` 提供；若容器停止，公网域名会出现上游不可用。

## Rollback

- 本机：移除 `~/.frpc/frpc.ini` 中 `[dsa-stock]` 段并重启 `frpc.service`。
- ECS2：恢复 `stock.conf` 备份并执行 `/usr/local/nginx/sbin/nginx -t && /usr/local/nginx/sbin/nginx -s reload`。
- 证书：不需要删除证书即可回滚 nginx；如需彻底清理，可另行删除 certbot 与 nginx 证书文件，但默认不做破坏性清理。
