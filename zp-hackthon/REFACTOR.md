# TicketHunter 重构说明

## 重构目标
从纯 Web 应用转型为**混合架构**——既保留 Web 界面供人操作，又提供 Skill 工具供 Agent 调用。

## 架构变化

### 重构前（纯 Web）
```
zp-hackthon/
├── app.py          # 所有逻辑混在一个文件
├── config.py       # 配置
├── database.py     # 数据库模型
├── mcp_client.py   # MCP 客户端
├── prompts.py      # AI 提示词
└── templates/      # 前端模板
```

### 重构后（混合架构）
```
zp-hackthon/
├── SKILL.md                    # Skill 说明文档
├── web/
│   ├── app.py                  # Flask 应用（精简版）
│   ├── templates/              # 前端模板
│   └── static/                 # 静态资源
├── services/
│   └── ticket_service.py       # 核心业务服务
├── clients/
│   └── xiaohongshu_mcp.py      # MCP 客户端
├── skill/
│   └── tools.py                # Agent Skill 工具
├── shared/
│   └── config.py               # 共享配置
├── database.py                 # 数据库模型（保留）
├── requirements.txt            # 依赖
└── .env.example                # 环境变量示例
```

## 核心改进

### 1. Service 层分离
- 所有业务逻辑提取到 `services/ticket_service.py`
- Web 和 Skill 共用同一套 `TicketService` 类
- 支持内存存储（无数据库时）和 SQLite 两种模式

### 2. Skill 工具集
Agent 可直接调用：
- `search_tickets(keyword)` - 搜索票务
- `analyze_ticket(content)` - 分析内容
- `start_monitoring(keyword, interval)` - 启动监控
- `list_tasks()` - 列出任务
- `stop_task(task_id)` - 停止任务

### 3. Web 层精简
- 从 600+ 行的 monolithic app.py 精简到 200+ 行
- 只保留路由和视图逻辑
- 业务逻辑全部委托给 Service 层

### 4. 配置现代化
- 支持 `.env` 环境变量
- 不再硬编码 API Key
- 支持 development/production 多环境

## 使用方式

### Web 界面（人操作）
```bash
cd zp-hackthon
cp .env.example .env
# 编辑 .env 填入 ZHIPU_API_KEY
pip install -r requirements.txt
python web/app.py
# 访问 http://localhost:5000
```

### Agent Skill（AI 调用）
```python
from skill.tools import search_tickets, start_monitoring

# Agent 直接搜索
result = search_tickets("周杰伦演唱会")

# Agent 启动监控
task_id = start_monitoring("陈奕迅香港演唱会", interval_min=60)

# Agent 查看任务
print(list_tasks())
```

## 人机协作场景

| 场景 | 人操作 | Agent 操作 |
|-----|--------|-----------|
| 临时查票 | Web 输入关键词 | Agent 调用 search_tickets |
| 批量监控 | Web 添加多个关键词 | Agent 批量启动任务 |
| 新票提醒 | 看 Web 页面闪烁 | Agent 收到推送后通知用户 |
| 复杂筛选 | Web 高级筛选 | Agent 自动分析后汇报 |

## 待完善

- [ ] 前端模板迁移到新路径
- [ ] 添加飞书/Discord 通知集成
- [ ] 支持 Bitable 云端存储
- [ ] 添加更多 Skill 工具（如导出 Excel）
- [ ] 定时任务持久化（APScheduler + Redis）

## 迁移检查清单

- [x] 提取 Service 层
- [x] 创建 Skill 工具
- [x] 重构 Web 层
- [x] 环境变量配置
- [ ] 复制前端模板到新位置
- [ ] 测试 Web 功能
- [ ] 测试 Skill 功能
- [ ] 更新 README
