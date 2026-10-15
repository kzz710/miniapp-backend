"""买车决策小程序 · 后端服务 (FastAPI)。

项目结构：
- config:       环境变量 / 配置
- types:        Pydantic 数据模型（入参 / 出参）
- engine:       纯函数计算引擎（落地价 / 月供 / 可负担性评估）
- services:     业务服务（车价检索增强 RAG、搜索、示例库兜底）
- utils:        通用工具（TTL 缓存、校验、辅助函数）
- main:         FastAPI 应用入口与路由
"""

__version__ = "0.1.0"
