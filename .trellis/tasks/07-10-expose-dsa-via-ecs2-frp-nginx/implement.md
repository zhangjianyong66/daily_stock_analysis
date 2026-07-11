# 通过 ECS2 frp 和 nginx 暴露本机 DSA 服务 - Implementation Plan

## Checklist

1. 记录当前状态
   - 本机：`docker compose -f ./docker/docker-compose.yml ps`
   - 本机：`systemctl --user status frpc.service`
   - ECS2：`pgrep -a nginx`、`systemctl status frps.service`、`ss -tulpn`

2. 本机配置 frpc
   - 备份 `~/.frpc/frpc.ini`。
   - 如果不存在 `[dsa-stock]`，追加 HTTP proxy 到本机 `127.0.0.1:8001`，`custom_domains = stock.zhangjianyong.top`。
   - 执行 `~/.local/bin/frpc verify -c ~/.frpc/frpc.ini`。
   - 重启 `systemctl --user restart frpc.service`。
   - 查看 `journalctl --user -u frpc.service -n 80 --no-pager`，确认新增代理启动成功且已有代理未失败。

3. ECS2 配置 nginx
   - 备份 `/usr/local/nginx/conf/conf.d/stock.conf`。
   - 写入新的 `stock.conf`，HTTP 处理 ACME challenge 和跳转，HTTPS 反代到 `127.0.0.1:8080`。
   - 执行 `/usr/local/nginx/sbin/nginx -t`。
   - 暂不 reload 前先处理证书文件有效性。

4. ECS2 更新单域名证书
   - 确认 `/root/ssl_auto_renew/domains.conf` 仍包含 `stock.zhangjianyong.top:/usr/local/nginx/conf/conf.d/stock.conf`。
   - 使用 webroot 方式只处理 `stock.zhangjianyong.top`。
   - 将 Let's Encrypt `fullchain.pem` / `privkey.pem` 拷贝到 nginx 现有证书路径。
   - 再次执行 `/usr/local/nginx/sbin/nginx -t`。
   - 执行 `/usr/local/nginx/sbin/nginx -s reload`。

5. 验证公网访问
   - `curl -I https://stock.zhangjianyong.top/` 不使用 `-k` 应通过证书校验。
   - `curl https://stock.zhangjianyong.top/api/v1/auth/status` 应返回 DSA API 响应。
   - 浏览器入口应加载 DSA Web 页面并进入 DSA 自身登录流程。

6. 文档更新
   - 更新 `AGENTS.md` 中本机 / ECS2 当前部署备注，记录最终公网入口、frpc proxy 名、nginx 配置路径和 SSL 续期入口。
   - 如同步维护 `/home/zhangjianyong/project/server_environment/docs/ecs2-environment.md`，只记录不含敏感信息的事实。

## Validation Commands

```bash
docker compose -f ./docker/docker-compose.yml ps
curl -I http://127.0.0.1:8001/
systemctl --user status frpc.service --no-pager
journalctl --user -u frpc.service -n 80 --no-pager
ssh root@ecs2.zhangjianyong.top '/usr/local/nginx/sbin/nginx -t'
curl -I https://stock.zhangjianyong.top/
curl https://stock.zhangjianyong.top/api/v1/auth/status
python3 scripts/check_ai_assets.py
```

## Rollback Points

- frpc 修改后失败：恢复 `~/.frpc/frpc.ini` 备份并重启用户级 `frpc.service`。
- nginx 检查失败：不 reload，恢复 `stock.conf` 备份。
- nginx reload 后公网异常：恢复 `stock.conf` 备份并 reload。
- 证书签发失败：保留 nginx 配置备份，不删除旧证书；根据 certbot 输出单独处理 DNS/HTTP-01/webroot 问题。
