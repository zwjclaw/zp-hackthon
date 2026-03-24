"""
OpenClaw Skill 工具集
Agent 通过调用这些工具与 TicketHunter 交互
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, List

from services.ticket_service import get_ticket_service

# 获取服务实例
ticket_service = get_ticket_service()


def search_tickets(keyword: str, limit: int = 10) -> str:
    """
    搜索票务信息
    
    Args:
        keyword: 搜索关键词，如"周杰伦演唱会"
        limit: 返回结果数量上限
        
    Returns:
        格式化的搜索结果
    """
    result = ticket_service.search_tickets(keyword, limit=limit)
    
    if not result['success']:
        return f"❌ 搜索失败: {result.get('error', '未知错误')}"
    
    tickets = result['tickets']
    keyword_info = result['keyword']
    if result['optimized_keyword'] != keyword:
        keyword_info += f" (优化为: {result['optimized_keyword']})"
    
    if not tickets:
        return f"🔍 搜索完成\n关键词: {keyword_info}\n结果: 未找到票务信息"
    
    # 格式化输出
    lines = [
        f"🎫 找到 {len(tickets)} 条票务信息",
        f"关键词: {keyword_info}",
        "-" * 40
    ]
    
    for i, ticket in enumerate(tickets, 1):
        lines.append(f"\n[{i}] {ticket.get('event_name', '未知活动')}")
        lines.append(f"   📍 城市: {ticket.get('city', '未知')}")
        lines.append(f"   📅 日期: {ticket.get('event_date') or '未定'}")
        lines.append(f"   🎟️ 区域: {ticket.get('area', '未知')}")
        lines.append(f"   💰 价格: {ticket.get('price', '未知')}")
        lines.append(f"   📦 数量: {ticket.get('quantity', '未知')}")
        lines.append(f"   📞 联系: {ticket.get('contact', '未知')}")
        if ticket.get('notes'):
            lines.append(f"   📝 备注: {ticket['notes']}")
        lines.append(f"   🔗 链接: {ticket.get('note_url', '')}")
    
    return "\n".join(lines)


def analyze_ticket(content: str) -> str:
    """
    分析内容是否为票务信息
    
    Args:
        content: 要分析的文本内容
        
    Returns:
        分析结果
    """
    result = ticket_service.analyze_ticket(content)
    
    if result['is_ticket']:
        ticket = result['ticket']
        return f"""✅ 这是一个票务转让信息

📌 活动: {ticket.get('event_name', '未知')}
📍 城市: {ticket.get('city', '未知')}
📅 日期: {ticket.get('event_date') or '未定'}
🎟️ 区域: {ticket.get('area', '未知')}
💰 价格: {ticket.get('price', '未知')}
📦 数量: {ticket.get('quantity', '未知')}
📞 联系: {ticket.get('contact', '未知')}
📝 备注: {ticket.get('notes', '无')}
🔗 链接: {ticket.get('note_url', '')}"""
    else:
        return "❌ 这不是票务转让信息"


def start_monitoring(keyword: str, interval_min: int = 60) -> str:
    """
    启动票务监控任务
    
    Args:
        keyword: 监控关键词
        interval_min: 检查间隔（分钟），默认 60
        
    Returns:
        任务启动结果
    """
    def on_new_ticket(ticket):
        """发现新票务时的回调"""
        # 这里可以接入通知系统（飞书、Discord 等）
        print(f"🎫 发现新票务: {ticket.get('event_name')}")
    
    task_id = ticket_service.start_monitoring(
        keyword=keyword,
        interval_seconds=interval_min * 60,
        on_new_ticket=on_new_ticket
    )
    
    optimized = ticket_service.optimize_keyword(keyword)
    keyword_info = keyword
    if optimized != keyword:
        keyword_info += f" (优化为: {optimized})"
    
    return f"""✅ 监控任务已启动

📝 任务ID: {task_id}
🔍 关键词: {keyword_info}
⏰ 间隔: {interval_min} 分钟
📊 状态: 运行中

提示: 使用 list_tasks() 查看所有任务
使用 stop_task("{task_id}") 停止此任务"""


def list_tasks() -> str:
    """
    列出所有监控任务
    
    Returns:
        任务列表
    """
    tasks = ticket_service.list_tasks()
    
    if not tasks:
        return "📋 暂无监控任务"
    
    lines = [f"📋 共 {len(tasks)} 个监控任务\n", "-" * 40]
    
    for task in tasks:
        status_emoji = "🟢" if task['status'] == 'running' else "🔴"
        lines.append(f"\n{status_emoji} 任务 {task['id']}")
        lines.append(f"   关键词: {task['optimized_keyword']}")
        lines.append(f"   状态: {task['status']}")
        lines.append(f"   检查次数: {task['run_count']}")
        lines.append(f"   发现票务: {task['ticket_count']}")
        if task['last_run_at']:
            lines.append(f"   上次执行: {task['last_run_at'].strftime('%Y-%m-%d %H:%M:%S')}")
    
    return "\n".join(lines)


def stop_task(task_id: str) -> str:
    """
    停止监控任务
    
    Args:
        task_id: 任务 ID
        
    Returns:
        操作结果
    """
    if ticket_service.stop_task(task_id):
        return f"✅ 任务 {task_id} 已停止"
    return f"❌ 任务 {task_id} 不存在或已停止"


def get_task_status(task_id: str) -> str:
    """
    获取任务状态
    
    Args:
        task_id: 任务 ID
        
    Returns:
        任务状态详情
    """
    task = ticket_service.get_task(task_id)
    
    if not task:
        return f"❌ 任务 {task_id} 不存在"
    
    status_emoji = "🟢" if task['status'] == 'running' else "🔴"
    
    lines = [
        f"{status_emoji} 任务 {task_id} 状态",
        "-" * 30,
        f"关键词: {task['optimized_keyword']}",
        f"状态: {task['status']}",
        f"间隔: {task['interval']} 秒",
        f"创建时间: {task['created_at'].strftime('%Y-%m-%d %H:%M:%S')}",
        f"执行次数: {task['run_count']}",
        f"发现票务: {task['ticket_count']}"
    ]
    
    if task['last_run_at']:
        lines.append(f"上次执行: {task['last_run_at'].strftime('%Y-%m-%d %H:%M:%S')}")
    
    return "\n".join(lines)


def execute_task_once(task_id: str) -> str:
    """
    立即执行一次任务（用于手动触发）
    
    Args:
        task_id: 任务 ID
        
    Returns:
        执行结果
    """
    result = ticket_service.execute_task_once(task_id)
    
    if not result['success']:
        return f"❌ 执行失败: {result.get('error', '未知错误')}"
    
    tickets = result.get('tickets', [])
    
    if not tickets:
        return "✅ 执行完成，未发现新票务"
    
    lines = [
        f"✅ 执行完成，发现 {len(tickets)} 条新票务",
        "-" * 40
    ]
    
    for i, ticket in enumerate(tickets, 1):
        lines.append(f"\n[{i}] {ticket.get('event_name', '未知活动')}")
        lines.append(f"   📍 {ticket.get('city', '未知')} | 💰 {ticket.get('price', '未知')}")
    
    return "\n".join(lines)
