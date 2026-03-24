"""
通用监控平台 Skill 工具
支持多模板、自定义任务类型、动态表单
"""

from typing import Dict, Any, List, Optional
from services.universal_monitor import (
    get_monitor_service, 
    FieldType,
    FieldDefinition,
    BUILTIN_TEMPLATES
)

# 获取服务实例
monitor_service = get_monitor_service()


def list_templates(category: str = None) -> str:
    """
    列出所有可用的监控模板
    
    Args:
        category: 按分类筛选（如：娱乐、招聘、交易、房产、优惠）
        
    Returns:
        模板列表
    """
    templates = monitor_service.list_templates(category)
    
    if not templates:
        return "📋 暂无模板"
    
    lines = [f"📋 共 {len(templates)} 个监控模板\n", "-" * 50]
    
    for t in templates:
        lines.append(f"\n{t.get('icon', '📝')} {t['name']} (ID: {t['id']})")
        lines.append(f"   📂 分类: {t['category']}")
        lines.append(f"   📝 {t['description']}")
        lines.append(f"   🔧 字段数: {len(t.get('fields', []))}")
        lines.append(f"   📡 数据源: {', '.join(t.get('default_data_sources', []))}")
    
    return "\n".join(lines)


def get_template_detail(template_id: str) -> str:
    """
    获取模板详细信息
    
    Args:
        template_id: 模板ID（如 ticket, job, secondhand）
        
    Returns:
        模板详情
    """
    template = monitor_service.get_template(template_id)
    
    if not template:
        return f"❌ 模板不存在: {template_id}"
    
    lines = [
        f"{template.icon} {template.name}",
        "=" * 50,
        f"ID: {template.id}",
        f"分类: {template.category}",
        f"描述: {template.description}",
        "",
        "📋 字段定义:",
        "-" * 50
    ]
    
    for field in template.fields:
        req_mark = " *" if field.required else ""
        lines.append(f"\n  • {field.label}{req_mark} ({field.name})")
        lines.append(f"    类型: {field.type.value}")
        if field.options:
            lines.append(f"    选项: {', '.join(field.options)}")
        if field.ai_extract_prompt:
            lines.append(f"    AI提取: {field.ai_extract_prompt[:50]}...")
    
    return "\n".join(lines)


def create_task(name: str,
                template_id: str,
                keywords: str,
                filters: str = None,
                interval_min: int = 60) -> str:
    """
    创建监控任务
    
    Args:
        name: 任务名称
        template_id: 模板ID（如 ticket, job, secondhand, house, coupon）
        keywords: 监控关键词，多个用逗号分隔（如"周杰伦演唱会,周杰伦门票"）
        filters: 过滤条件（JSON格式），如 {"city": "北京", "price_max": 1000}
        interval_min: 检查间隔（分钟），默认60
        
    Returns:
        任务创建结果
    """
    try:
        # 解析关键词
        keyword_list = [k.strip() for k in keywords.split(',') if k.strip()]
        if not keyword_list:
            return "❌ 关键词不能为空"
        
        # 解析过滤条件
        filter_dict = {}
        if filters:
            import json
            try:
                filter_dict = json.loads(filters)
            except:
                return "❌ 过滤条件格式错误，应为JSON格式"
        
        # 创建任务
        task = monitor_service.create_task(
            name=name,
            template_id=template_id,
            keywords=keyword_list,
            filters=filter_dict,
            interval_minutes=interval_min
        )
        
        template = monitor_service.get_template(template_id)
        
        lines = [
            f"✅ 监控任务已创建",
            "",
            f"📝 任务名称: {task.name}",
            f"🆔 任务ID: {task.id}",
            f"📋 使用模板: {template.name if template else template_id}",
            f"🔍 关键词: {', '.join(task.keywords)}",
        ]
        
        if filter_dict:
            lines.append(f"🔧 过滤条件: {filters}")
        
        lines.extend([
            f"⏰ 检查间隔: {interval_min} 分钟",
            f"📊 状态: {task.status}",
            "",
            "提示:",
            f"  • 使用 execute_task('{task.id}') 立即执行",
            f"  • 使用 list_tasks() 查看所有任务",
            f"  • 使用 stop_task('{task.id}') 停止任务"
        ])
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"❌ 创建任务失败: {e}"


def list_tasks(status: str = None) -> str:
    """
    列出所有监控任务
    
    Args:
        status: 按状态筛选（running, paused, stopped）
        
    Returns:
        任务列表
    """
    tasks = monitor_service.list_tasks(status)
    
    if not tasks:
        return "📋 暂无监控任务"
    
    lines = [f"📋 共 {len(tasks)} 个监控任务\n", "-" * 50]
    
    for t in tasks:
        status_emoji = {
            'running': '🟢',
            'paused': '⏸️',
            'stopped': '🔴'
        }.get(t['status'], '⚪')
        
        template = monitor_service.get_template(t['template_id'])
        template_icon = template.icon if template else '📝'
        
        lines.append(f"\n{status_emoji} {template_icon} {t['name']} (ID: {t['id']})")
        lines.append(f"   模板: {template.name if template else t['template_id']}")
        lines.append(f"   关键词: {', '.join(t['keywords'])}")
        lines.append(f"   状态: {t['status']}")
        lines.append(f"   执行次数: {t['run_count']}")
        lines.append(f"   匹配次数: {t['match_count']}")
        
        if t['last_run_at']:
            lines.append(f"   上次执行: {t['last_run_at']}")
    
    return "\n".join(lines)


def execute_task(task_id: str) -> str:
    """
    立即执行一次监控任务
    
    Args:
        task_id: 任务ID
        
    Returns:
        执行结果
    """
    import json
    
    try:
        matches = monitor_service.execute_task(task_id)
        
        if not matches:
            return f"✅ 任务 {task_id} 执行完成\n未发现新的匹配项"
        
        lines = [
            f"✅ 任务 {task_id} 执行完成",
            f"发现 {len(matches)} 条匹配:\n",
            "-" * 50
        ]
        
        for i, match in enumerate(matches, 1):
            lines.append(f"\n[{i}] {match.summary}")
            lines.append(f"   置信度: {match.confidence:.0%}")
            lines.append(f"   链接: {match.source_url}")
            
            if match.extracted_fields:
                lines.append("   提取信息:")
                for key, value in match.extracted_fields.items():
                    if value:
                        lines.append(f"     • {key}: {value}")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"❌ 执行失败: {e}"


def stop_task(task_id: str) -> str:
    """停止任务"""
    if monitor_service.stop_task(task_id):
        return f"✅ 任务 {task_id} 已停止"
    return f"❌ 任务 {task_id} 不存在"


def pause_task(task_id: str) -> str:
    """暂停任务"""
    if monitor_service.pause_task(task_id):
        return f"⏸️ 任务 {task_id} 已暂停"
    return f"❌ 任务 {task_id} 不存在"


def resume_task(task_id: str) -> str:
    """恢复任务"""
    if monitor_service.resume_task(task_id):
        return f"▶️ 任务 {task_id} 已恢复"
    return f"❌ 任务 {task_id} 不存在"


def delete_task(task_id: str) -> str:
    """删除任务"""
    if monitor_service.delete_task(task_id):
        return f"🗑️ 任务 {task_id} 已删除"
    return f"❌ 任务 {task_id} 不存在"


def get_task_detail(task_id: str) -> str:
    """获取任务详情"""
    task = monitor_service.get_task(task_id)
    
    if not task:
        return f"❌ 任务不存在: {task_id}"
    
    template = monitor_service.get_template(task.template_id)
    
    lines = [
        f"📝 {task.name}",
        "=" * 50,
        f"任务ID: {task.id}",
        f"模板: {template.name if template else task.template_id}",
        f"状态: {task.status}",
        f"关键词: {', '.join(task.keywords)}",
        f"数据源: {', '.join(task.data_sources)}",
        f"检查间隔: {task.interval_seconds // 60} 分钟",
        f"最小置信度: {task.min_confidence:.0%}",
        "",
        "统计:",
        f"  创建时间: {task.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"  执行次数: {task.run_count}",
        f"  匹配次数: {task.match_count}"
    ]
    
    if task.last_run_at:
        lines.append(f"  上次执行: {task.last_run_at.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if task.filters:
        lines.append(f"\n过滤条件: {task.filters}")
    
    return "\n".join(lines)


def analyze_content(content: str, template_id: str) -> str:
    """
    分析内容是否匹配指定模板
    
    Args:
        content: 要分析的内容
        template_id: 模板ID
        
    Returns:
        分析结果
    """
    template = monitor_service.get_template(template_id)
    
    if not template:
        return f"❌ 模板不存在: {template_id}"
    
    # 创建一个临时任务来执行分析
    from services.universal_monitor import MonitoringTask, MatchResult
    
    temp_task = MonitoringTask(
        id="temp",
        name="temp",
        template_id=template_id,
        keywords=[],
        min_confidence=0.0
    )
    
    result = monitor_service._analyze_content(content, template, temp_task)
    
    lines = [
        f"🔍 内容分析结果",
        "=" * 50,
        f"模板: {template.name}",
        f"是否匹配: {'✅ 是' if result.is_match else '❌ 否'}",
        f"置信度: {result.confidence:.0%}",
    ]
    
    if result.summary:
        lines.append(f"摘要: {result.summary}")
    
    if result.extracted_fields:
        lines.append("\n提取的字段:")
        lines.append("-" * 50)
        for key, value in result.extracted_fields.items():
            # 查找字段定义获取中文名
            field_def = next((f for f in template.fields if f.name == key), None)
            label = field_def.label if field_def else key
            lines.append(f"  {label}: {value}")
    
    return "\n".join(lines)


def create_custom_template(name: str,
                           description: str,
                           category: str,
                           fields_json: str,
                           icon: str = "📝") -> str:
    """
    创建自定义监控模板
    
    Args:
        name: 模板名称
        description: 模板描述
        category: 分类
        fields_json: 字段定义（JSON数组），示例:
            [
                {"name": "title", "label": "标题", "type": "text", "required": true},
                {"name": "price", "label": "价格", "type": "price"}
            ]
        icon: 模板图标
        
    Returns:
        创建结果
    """
    import json
    
    try:
        fields = json.loads(fields_json)
        
        template = monitor_service.create_custom_template(
            name=name,
            description=description,
            category=category,
            fields=fields,
            icon=icon
        )
        
        return f"""✅ 自定义模板已创建

📝 {template.name}
ID: {template.id}
描述: {template.description}
分类: {template.category}
字段数: {len(template.fields)}

现在可以使用此模板创建任务:
create_task("我的任务", "{template.id}", "关键词")"""
        
    except Exception as e:
        return f"❌ 创建模板失败: {e}"


# 快捷命令
def quick_ticket(keyword: str, city: str = None, max_price: int = None) -> str:
    """
    快速创建票务监控任务（快捷命令）
    
    Args:
        keyword: 关键词（如"周杰伦演唱会"）
        city: 城市过滤（可选）
        max_price: 最高价格（可选）
    """
    filters = {}
    if city:
        filters['city'] = city
    if max_price:
        filters['price_max'] = max_price
    
    import json
    filters_str = json.dumps(filters) if filters else None
    
    return create_task(
        name=f"{keyword}票务监控",
        template_id="ticket",
        keywords=keyword,
        filters=filters_str,
        interval_min=30
    )


def quick_job(keyword: str, location: str = None, job_type: str = None) -> str:
    """
    快速创建招聘监控任务（快捷命令）
    
    Args:
        keyword: 关键词（如"Python工程师"）
        location: 地点过滤（可选）
        job_type: 工作类型（全职/兼职/实习/远程）
    """
    filters = {}
    if location:
        filters['location_contains'] = location
    if job_type:
        filters['job_type'] = job_type
    
    import json
    filters_str = json.dumps(filters) if filters else None
    
    return create_task(
        name=f"{keyword}招聘监控",
        template_id="job",
        keywords=keyword,
        filters=filters_str,
        interval_min=60
    )


def quick_secondhand(item: str, category: str = None, max_price: int = None) -> str:
    """
    快速创建二手交易监控任务（快捷命令）
    
    Args:
        item: 物品名称（如"iPhone 15"）
        category: 分类（数码/家电/服饰/图书/家居/美妆/运动）
        max_price: 最高价格
    """
    filters = {}
    if category:
        filters['category'] = category
    if max_price:
        filters['price_max'] = max_price
    
    import json
    filters_str = json.dumps(filters) if filters else None
    
    return create_task(
        name=f"{item}二手监控",
        template_id="secondhand",
        keywords=item,
        filters=filters_str,
        interval_min=30
    )
