"""
TicketHunter - 票务监控系统
混合架构版本：Web + Skill 双模态

架构：
- Web 层: Flask + Bootstrap 前端
- Service 层: 核心业务逻辑（Web 和 Skill 共用）
- Skill 层: OpenClaw Skill 工具集
- 数据层: SQLite（本地）/ Bitable（云端可选）
"""

__version__ = "2.0.0"
__author__ = "TicketHunter Team"
