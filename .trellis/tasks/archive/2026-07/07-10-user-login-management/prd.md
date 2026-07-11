# 增加用户登录和用户管理

## Goal

为 Web 工作台增加多用户登录与管理员用户管理能力。系统默认提供一个 `admin` 管理员用户，管理员密码来自 `.env` 配置；普通用户不能自行注册，只能由管理员在用户管理页面创建。

## Confirmed Facts

- 现有后端已有单管理员认证模块 `src/auth.py`，使用 `ADMIN_AUTH_ENABLED` 控制是否启用，登录后写入 `dsa_session` HttpOnly Cookie。
- 现有登录 API 位于 `api/v1/endpoints/auth.py`，包含 `/status`、`/login`、`/logout`、`/change-password`、`/settings`。
- 现有中间件 `api/middlewares/auth.py` 在 `ADMIN_AUTH_ENABLED=true` 时保护 `/api/v1/*`，豁免登录、状态、健康检查和 OpenAPI 文档。
- 当前会话 Cookie 只校验签名和过期时间，不包含用户名或角色；多用户需要升级会话载荷并在后端可读取当前用户身份。
- 现有前端已有 `LoginPage`、`AuthContext`、认证状态刷新、未登录重定向、登出按钮和设置页认证组件。
- 现有侧边栏菜单在 `apps/dsa-web/src/components/layout/SidebarNav.tsx` 中集中定义，新增“用户管理”菜单应按现有导航模式接入。
- 项目使用 SQLite + SQLAlchemy，数据库模型集中在 `src/storage.py`，仓储层放在 `src/repositories/`，服务层放在 `src/services/`。
- 新配置项必须同步 `.env.example`、相关文档和 `docs/CHANGELOG.md`。

## Requirements

- 默认存在用户名为 `admin` 的管理员账号。
- 管理员密码从 `.env` 配置读取，不再依赖网页首次设置管理员密码作为默认路径。
- 登录页不提供注册入口。
- 用户只能由管理员添加。
- 管理员登录后可看到用户管理菜单。
- 普通用户不能看到或调用用户管理能力。
- 多用户认证必须继续使用 HttpOnly Cookie，不引入前端可读 token。

## Acceptance Criteria

- [ ] 配置 `.env` 后，`admin` 可用配置的管理员密码登录。
- [ ] 未登录用户访问受保护 Web 页面会被重定向到登录页。
- [ ] 管理员可在 Web 用户管理页查看、创建、禁用或删除普通用户，并可设置用户密码。
- [ ] 普通用户登录后不能看到用户管理菜单，直接请求用户管理 API 会返回 403。
- [ ] 系统不提供公开注册 API 或注册页面。
- [ ] 既有 `/api/v1/*` 认证保护继续生效，健康检查和登录状态接口仍按现有豁免规则可访问。
- [ ] `.env.example`、相关文档和 `docs/CHANGELOG.md` 已同步说明新登录与用户管理行为。

## Notes

- 2026-07-10：用户确认仓库已存在登录功能，本任务放弃，不进入设计或实现阶段。
- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
