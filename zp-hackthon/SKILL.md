# TicketHunter Skill

混合架构版本的票务监控 Skill，支持 Web 界面和 Agent 调用。

## 架构

```
tickethunter/
├── web/              # Web 层 (Flask + 前端)
├── services/         # 业务服务层 (Web 和 Skill 共用)
├── clients/          # 外部客户端封装
├── skill/            # OpenClaw Skill 工具
└── shared/           # 共享配置
```

## 使用方式

### 1. Web 界面

启动 Web 服务：
```bash
python web/app.py
```

访问 http://localhost:5000

### 2. Agent Skill

```python
from skill.tools import search_tickets, start_monitoring

# 搜索票务
result = search_tickets("周杰伦演唱会")

# 启动监控
task_id = start_monitoring("陈奕迅香港演唱会", interval_min=60)
```

## 环境变量

- `ZHIPU_API_KEY`: 智谱 AI API Key
- `MCP_XIAOHONGSHU_URL`: 小红书 MCP 服务地址

## 依赖

- Flask
- requests
- sseclient-py
- apscheduler (可选，用于定时任务)
