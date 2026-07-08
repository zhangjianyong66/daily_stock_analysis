# 通用思考指南

本目录是跨层改动前的检查清单，不替代 `backend/` 下的项目规范。实际编码规则以 `AGENTS.md` 和 `.trellis/spec/backend/*.md` 为准。

## 可用指南

| 指南 | 使用场景 |
| --- | --- |
| [Code Reuse Thinking Guide](./code-reuse-thinking-guide.md) | 新增 helper、配置项、字段、payload 解析、重复逻辑前先读 |
| [Cross-Layer Thinking Guide](./cross-layer-thinking-guide.md) | 改动跨 CLI/API/Web/Desktop/DB/Workflow/Docs 多层时先读 |

## 本项目触发点

需要先考虑代码复用：

- 新增或修改配置项。
- 新增工具函数、数据源 fallback、字段解析、股票代码规范化逻辑。
- 在两个以上入口读取同一个 API payload、JSON、事件字段或配置字段。
- 复制已有 service/repository/endpoint 流程。

需要先考虑跨层契约：

- API schema、前端类型、桌面端、Bot 命令、报告结构之间有字段变化。
- `.env.example`、Web 设置页、Docker、GitHub Actions 同时依赖同一配置。
- 数据源 fallback、通知链路、LLM 参数、报告渲染影响多个运行入口。
- 工作流、发布、Docker、桌面端打包路径发生变化。

## 使用方式

开始改动前按任务选择阅读；发现指南中的 Trellis 通用示例与本仓库不一致时，以本仓库 `backend/` 规范、实际代码、脚本和 workflow 为准。
