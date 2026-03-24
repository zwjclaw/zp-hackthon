"""
通用任务监控平台 - 核心服务
支持自定义任务类型、动态字段、多数据源
"""

import os
import sys
import json
import logging
import requests
import sseclient
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable, Union
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from dataclasses import dataclass, field, asdict
from enum import Enum

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FieldType(Enum):
    """字段类型枚举"""
    TEXT = "text"           # 单行文本
    TEXTAREA = "textarea"   # 多行文本
    NUMBER = "number"       # 数字
    SELECT = "select"       # 单选
    MULTI_SELECT = "multi_select"  # 多选
    DATE = "date"           # 日期
    DATETIME = "datetime"   # 日期时间
    BOOLEAN = "boolean"     # 布尔
    URL = "url"             # 链接
    PRICE = "price"         # 价格（特殊格式）
    CONTACT = "contact"     # 联系方式
    TAGS = "tags"           # 标签


@dataclass
class FieldDefinition:
    """字段定义"""
    name: str                          # 字段名（英文，用于代码）
    label: str                         # 字段显示名（中文）
    type: FieldType                    # 字段类型
    required: bool = False             # 是否必填
    options: List[str] = field(default_factory=list)  # 选项（用于select类型）
    placeholder: str = ""              # 占位提示
    default_value: Any = None          # 默认值
    ai_extract_prompt: str = ""        # AI 提取提示词（用于从内容中提取）
    validation_regex: str = ""         # 验证正则
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'label': self.label,
            'type': self.type.value,
            'required': self.required,
            'options': self.options,
            'placeholder': self.placeholder,
            'default_value': self.default_value,
            'ai_extract_prompt': self.ai_extract_prompt,
            'validation_regex': self.validation_regex
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FieldDefinition':
        return cls(
            name=data['name'],
            label=data['label'],
            type=FieldType(data['type']),
            required=data.get('required', False),
            options=data.get('options', []),
            placeholder=data.get('placeholder', ''),
            default_value=data.get('default_value'),
            ai_extract_prompt=data.get('ai_extract_prompt', ''),
            validation_regex=data.get('validation_regex', '')
        )


@dataclass
class TaskTemplate:
    """任务模板定义"""
    id: str                            # 模板ID
    name: str                          # 模板名称
    description: str                   # 模板描述
    category: str                      # 分类（如：票务、招聘、二手交易）
    icon: str = "📝"                   # 图标
    fields: List[FieldDefinition] = field(default_factory=list)  # 字段定义
    
    # AI 分析配置
    ai_analysis_prompt: str = ""       # AI 分析提示词模板
    is_match_prompt: str = ""          # 判断是否匹配任务的提示词
    
    # 数据源配置
    default_data_sources: List[str] = field(default_factory=lambda: ["xiaohongshu"])
    
    # 通知配置
    notification_rules: Dict[str, Any] = field(default_factory=dict)
    
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'icon': self.icon,
            'fields': [f.to_dict() for f in self.fields],
            'ai_analysis_prompt': self.ai_analysis_prompt,
            'is_match_prompt': self.is_match_prompt,
            'default_data_sources': self.default_data_sources,
            'notification_rules': self.notification_rules,
            'created_at': self.created_at.isoformat()
        }


# 预置模板库
BUILTIN_TEMPLATES = {
    "ticket": TaskTemplate(
        id="ticket",
        name="票务监控",
        description="监控演唱会、演出、活动票务转让信息",
        category="娱乐",
        icon="🎫",
        fields=[
            FieldDefinition(
                name="event_name",
                label="活动名称",
                type=FieldType.TEXT,
                required=True,
                ai_extract_prompt="提取演出或活动名称，如'周杰伦演唱会'"
            ),
            FieldDefinition(
                name="city",
                label="城市",
                type=FieldType.TEXT,
                ai_extract_prompt="提取城市名称"
            ),
            FieldDefinition(
                name="event_date",
                label="活动日期",
                type=FieldType.DATE,
                ai_extract_prompt="提取活动日期，格式YYYY-MM-DD，不确定则为空"
            ),
            FieldDefinition(
                name="venue",
                label="场馆",
                type=FieldType.TEXT,
                ai_extract_prompt="提取演出场馆名称"
            ),
            FieldDefinition(
                name="area",
                label="座位区域",
                type=FieldType.TEXT,
                ai_extract_prompt="提取座位区域或票价档位"
            ),
            FieldDefinition(
                name="price",
                label="转让价格",
                type=FieldType.PRICE,
                ai_extract_prompt="提取转让价格，保留数字和单位"
            ),
            FieldDefinition(
                name="quantity",
                label="数量",
                type=FieldType.NUMBER,
                ai_extract_prompt="提取票数"
            ),
            FieldDefinition(
                name="original_price",
                label="原价",
                type=FieldType.PRICE,
                ai_extract_prompt="提取原价信息"
            ),
            FieldDefinition(
                name="transfer_method",
                label="转让方式",
                type=FieldType.SELECT,
                options=["电子票", "实体票", "面交", "邮寄", "官方转赠"],
                ai_extract_prompt="提取转让方式"
            ),
            FieldDefinition(
                name="contact",
                label="联系方式",
                type=FieldType.CONTACT,
                ai_extract_prompt="提取联系方式，进行脱敏处理（如138****8888）"
            ),
            FieldDefinition(
                name="notes",
                label="备注",
                type=FieldType.TEXTAREA,
                ai_extract_prompt="提取其他重要信息"
            ),
            FieldDefinition(
                name="urgency",
                label="紧急程度",
                type=FieldType.SELECT,
                options=["急出", "可议", "不急"],
                ai_extract_prompt="判断紧急程度"
            )
        ],
        ai_analysis_prompt="""分析以下内容是否为演出/活动票务转让信息。
如果是，提取关键信息并以JSON格式返回。
内容：{content}

需要提取的字段：
{fields}

返回格式：
{{
    "is_match": true/false,
    "confidence": 0.0-1.0,
    "extracted_fields": {{
        "字段名": "提取的值"
    }},
    "summary": "一句话摘要"
}}"""
    ),
    
    "job": TaskTemplate(
        id="job",
        name="招聘信息监控",
        description="监控求职、招聘信息",
        category="招聘",
        icon="💼",
        fields=[
            FieldDefinition(
                name="position",
                label="职位",
                type=FieldType.TEXT,
                required=True,
                ai_extract_prompt="提取职位名称"
            ),
            FieldDefinition(
                name="company",
                label="公司",
                type=FieldType.TEXT,
                ai_extract_prompt="提取公司名称"
            ),
            FieldDefinition(
                name="location",
                label="工作地点",
                type=FieldType.TEXT,
                ai_extract_prompt="提取工作地点"
            ),
            FieldDefinition(
                name="salary",
                label="薪资",
                type=FieldType.TEXT,
                ai_extract_prompt="提取薪资范围"
            ),
            FieldDefinition(
                name="job_type",
                label="工作类型",
                type=FieldType.SELECT,
                options=["全职", "兼职", "实习", "远程"],
                ai_extract_prompt="提取工作类型"
            ),
            FieldDefinition(
                name="requirements",
                label="要求",
                type=FieldType.TEXTAREA,
                ai_extract_prompt="提取岗位要求"
            ),
            FieldDefinition(
                name="benefits",
                label="福利",
                type=FieldType.TEXTAREA,
                ai_extract_prompt="提取福利待遇"
            ),
            FieldDefinition(
                name="contact",
                label="联系方式",
                type=FieldType.CONTACT,
                ai_extract_prompt="提取联系方式"
            )
        ]
    ),
    
    "secondhand": TaskTemplate(
        id="secondhand",
        name="二手交易监控",
        description="监控二手物品买卖信息",
        category="交易",
        icon="📦",
        fields=[
            FieldDefinition(
                name="item_name",
                label="物品名称",
                type=FieldType.TEXT,
                required=True,
                ai_extract_prompt="提取物品名称"
            ),
            FieldDefinition(
                name="category",
                label="物品分类",
                type=FieldType.SELECT,
                options=["数码", "家电", "服饰", "图书", "家居", "美妆", "运动", "其他"],
                ai_extract_prompt="判断物品分类"
            ),
            FieldDefinition(
                name="condition",
                label="成色",
                type=FieldType.SELECT,
                options=["全新", "99新", "95新", "9成新", "8成新", "战损"],
                ai_extract_prompt="提取成色描述"
            ),
            FieldDefinition(
                name="price",
                label="价格",
                type=FieldType.PRICE,
                required=True,
                ai_extract_prompt="提取价格"
            ),
            FieldDefinition(
                name="original_price",
                label="原价",
                type=FieldType.PRICE,
                ai_extract_prompt="提取原价"
            ),
            FieldDefinition(
                name="location",
                label="所在地区",
                type=FieldType.TEXT,
                ai_extract_prompt="提取地区"
            ),
            FieldDefinition(
                name="shipping",
                label="发货方式",
                type=FieldType.SELECT,
                options=[["自提", "快递", "面交", "包邮", "到付"]],
                ai_extract_prompt="提取发货方式"
            ),
            FieldDefinition(
                name="description",
                label="物品描述",
                type=FieldType.TEXTAREA,
                ai_extract_prompt="提取物品描述"
            ),
            FieldDefinition(
                name="contact",
                label="联系方式",
                type=FieldType.CONTACT,
                ai_extract_prompt="提取联系方式"
            )
        ]
    ),
    
    "house": TaskTemplate(
        id="house",
        name="租房/房源监控",
        description="监控租房、房源信息",
        category="房产",
        icon="🏠",
        fields=[
            FieldDefinition(
                name="title",
                label="房源标题",
                type=FieldType.TEXT,
                required=True,
                ai_extract_prompt="提取房源标题"
            ),
            FieldDefinition(
                name="type",
                label="房源类型",
                type=FieldType.SELECT,
                options=["整租", "合租", "短租", "转租"],
                ai_extract_prompt="提取房源类型"
            ),
            FieldDefinition(
                name="city",
                label="城市",
                type=FieldType.TEXT,
                ai_extract_prompt="提取城市"
            ),
            FieldDefinition(
                name="district",
                label="区域",
                type=FieldType.TEXT,
                ai_extract_prompt="提取区域/区县"
            ),
            FieldDefinition(
                name="area",
                label="面积",
                type=FieldType.TEXT,
                ai_extract_prompt="提取面积，如'80平米'"
            ),
            FieldDefinition(
                name="rooms",
                label="户型",
                type=FieldType.TEXT,
                ai_extract_prompt="提取户型，如'两室一厅'"
            ),
            FieldDefinition(
                name="price",
                label="租金",
                type=FieldType.PRICE,
                required=True,
                ai_extract_prompt="提取租金"
            ),
            FieldDefinition(
                name="deposit",
                label="押金方式",
                type=FieldType.SELECT,
                options=["押一付一", "押一付三", "押二付一", "面议"],
                ai_extract_prompt="提取押金支付方式"
            ),
            FieldDefinition(
                name="facilities",
                label="配套设施",
                type=FieldType.MULTI_SELECT,
                options=["空调", "冰箱", "洗衣机", "热水器", "宽带", "暖气", "独卫", "阳台", "厨房"],
                ai_extract_prompt="提取配套设施"
            ),
            FieldDefinition(
                name="contact",
                label="联系方式",
                type=FieldType.CONTACT,
                ai_extract_prompt="提取联系方式"
            )
        ]
    ),
    
    "coupon": TaskTemplate(
        id="coupon",
        name="优惠券/羊毛监控",
        description="监控优惠信息、羊毛活动",
        category="优惠",
        icon="🎟️",
        fields=[
            FieldDefinition(
                name="platform",
                label="平台",
                type=FieldType.TEXT,
                ai_extract_prompt="提取平台名称，如'淘宝'、'京东'"
            ),
            FieldDefinition(
                name="title",
                label="优惠标题",
                type=FieldType.TEXT,
                required=True,
                ai_extract_prompt="提取优惠标题"
            ),
            FieldDefinition(
                name="discount",
                label="优惠力度",
                type=FieldType.TEXT,
                ai_extract_prompt="提取优惠力度，如'5折'、'满100减20'"
            ),
            FieldDefinition(
                name="original_price",
                label="原价",
                type=FieldType.PRICE,
                ai_extract_prompt="提取原价"
            ),
            FieldDefinition(
                name="current_price",
                label="现价",
                type=FieldType.PRICE,
                ai_extract_prompt="提取现价"
            ),
            FieldDefinition(
                name="valid_until",
                label="有效期至",
                type=FieldType.DATE,
                ai_extract_prompt="提取有效期"
            ),
            FieldDefinition(
                name="link",
                label="链接",
                type=FieldType.URL,
                ai_extract_prompt="提取链接"
            ),
            FieldDefinition(
                name="description",
                label="说明",
                type=FieldType.TEXTAREA,
                ai_extract_prompt="提取使用说明"
            )
        ]
    )
}


@dataclass
class MonitoringTask:
    """监控任务实例"""
    id: str
    name: str                           # 任务名称
    template_id: str                    # 使用的模板ID
    keywords: List[str]                 # 监控关键词列表
    
    # 筛选条件
    filters: Dict[str, Any] = field(default_factory=dict)  # 字段过滤条件
    min_confidence: float = 0.7         # 最小匹配置信度
    
    # 监控配置
    interval_seconds: int = 3600        # 检查间隔
    data_sources: List[str] = field(default_factory=list)   # 数据源
    
    # 状态
    status: str = "running"             # running, paused, stopped
    created_at: datetime = field(default_factory=datetime.now)
    last_run_at: Optional[datetime] = None
    run_count: int = 0
    match_count: int = 0
    
    # 回调
    on_match: Optional[Callable[[dict], None]] = None
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'template_id': self.template_id,
            'keywords': self.keywords,
            'filters': self.filters,
            'min_confidence': self.min_confidence,
            'interval_seconds': self.interval_seconds,
            'data_sources': self.data_sources,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'last_run_at': self.last_run_at.isoformat() if self.last_run_at else None,
            'run_count': self.run_count,
            'match_count': self.match_count
        }


@dataclass
class MatchResult:
    """匹配结果"""
    task_id: str
    source_id: str                    # 数据源ID（如小红书note_id）
    source_url: str                   # 来源链接
    source_content: str               # 原始内容
    template_id: str                  # 使用的模板
    
    is_match: bool                    # 是否匹配
    confidence: float                 # 置信度
    extracted_fields: Dict[str, Any]  # 提取的字段
    summary: str                      # 摘要
    
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            'task_id': self.task_id,
            'source_id': self.source_id,
            'source_url': self.source_url,
            'source_content': self.source_content[:200] + '...' if len(self.source_content) > 200 else self.source_content,
            'template_id': self.template_id,
            'is_match': self.is_match,
            'confidence': self.confidence,
            'extracted_fields': self.extracted_fields,
            'summary': self.summary,
            'created_at': self.created_at.isoformat()
        }


class TemplateManager:
    """模板管理器"""
    
    def __init__(self):
        self._templates: Dict[str, TaskTemplate] = {}
        self._load_builtin_templates()
    
    def _load_builtin_templates(self):
        """加载预置模板"""
        for template in BUILTIN_TEMPLATES.values():
            self._templates[template.id] = template
        logger.info(f"已加载 {len(self._templates)} 个预置模板")
    
    def get_template(self, template_id: str) -> Optional[TaskTemplate]:
        """获取模板"""
        return self._templates.get(template_id)
    
    def list_templates(self, category: str = None) -> List[TaskTemplate]:
        """列出模板"""
        templates = list(self._templates.values())
        if category:
            templates = [t for t in templates if t.category == category]
        return templates
    
    def create_template(self, template: TaskTemplate) -> TaskTemplate:
        """创建新模板"""
        if template.id in self._templates:
            raise ValueError(f"模板ID已存在: {template.id}")
        self._templates[template.id] = template
        logger.info(f"创建模板: {template.id}")
        return template
    
    def update_template(self, template_id: str, **kwargs) -> TaskTemplate:
        """更新模板"""
        template = self._templates.get(template_id)
        if not template:
            raise ValueError(f"模板不存在: {template_id}")
        
        for key, value in kwargs.items():
            if hasattr(template, key):
                setattr(template, key, value)
        
        logger.info(f"更新模板: {template_id}")
        return template
    
    def delete_template(self, template_id: str) -> bool:
        """删除模板（不能删除预置模板）"""
        if template_id in BUILTIN_TEMPLATES:
            raise ValueError(f"不能删除预置模板: {template_id}")
        
        if template_id in self._templates:
            del self._templates[template_id]
            logger.info(f"删除模板: {template_id}")
            return True
        return False


class UniversalMonitorService:
    """
    通用监控服务
    支持多模板、多数据源、动态字段提取
    """
    
    def __init__(self, zhipu_api_key: str, mcp_url: str = "http://localhost:18060/mcp"):
        self.zhipu_api_key = zhipu_api_key
        self.mcp_url = mcp_url
        
        self.template_manager = TemplateManager()
        self._tasks: Dict[str, MonitoringTask] = {}
        self._task_counter = 1
        self._lock = Lock()
        
        logger.info("UniversalMonitorService 初始化完成")
    
    # ============ 模板操作 ============
    
    def get_template(self, template_id: str) -> Optional[TaskTemplate]:
        """获取模板"""
        return self.template_manager.get_template(template_id)
    
    def list_templates(self, category: str = None) -> List[dict]:
        """列出所有模板"""
        templates = self.template_manager.list_templates(category)
        return [t.to_dict() for t in templates]
    
    def create_custom_template(self, 
                               name: str,
                               description: str,
                               category: str,
                               fields: List[dict],
                               icon: str = "📝") -> TaskTemplate:
        """创建自定义模板"""
        template_id = f"custom_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        field_defs = [FieldDefinition.from_dict(f) for f in fields]
        
        template = TaskTemplate(
            id=template_id,
            name=name,
            description=description,
            category=category,
            icon=icon,
            fields=field_defs
        )
        
        return self.template_manager.create_template(template)
    
    # ============ 任务操作 ============
    
    def create_task(self,
                    name: str,
                    template_id: str,
                    keywords: List[str],
                    filters: Dict[str, Any] = None,
                    interval_minutes: int = 60,
                    min_confidence: float = 0.7,
                    on_match: Callable[[dict], None] = None) -> MonitoringTask:
        """
        创建监控任务
        
        Args:
            name: 任务名称
            template_id: 模板ID
            keywords: 监控关键词列表
            filters: 字段过滤条件，如 {"city": "北京", "price_max": 500}
            interval_minutes: 检查间隔（分钟）
            min_confidence: 最小匹配置信度
            on_match: 匹配回调函数
        """
        # 验证模板存在
        template = self.template_manager.get_template(template_id)
        if not template:
            raise ValueError(f"模板不存在: {template_id}")
        
        with self._lock:
            task_id = f"task_{self._task_counter}"
            self._task_counter += 1
        
        task = MonitoringTask(
            id=task_id,
            name=name,
            template_id=template_id,
            keywords=keywords,
            filters=filters or {},
            interval_seconds=interval_minutes * 60,
            min_confidence=min_confidence,
            data_sources=template.default_data_sources.copy(),
            on_match=on_match
        )
        
        self._tasks[task_id] = task
        logger.info(f"创建任务: {task_id} ({name}) 使用模板: {template_id}")
        
        return task
    
    def get_task(self, task_id: str) -> Optional[MonitoringTask]:
        """获取任务"""
        return self._tasks.get(task_id)
    
    def list_tasks(self, status: str = None) -> List[dict]:
        """列出任务"""
        tasks = self._tasks.values()
        if status:
            tasks = [t for t in tasks if t.status == status]
        return [t.to_dict() for t in tasks]
    
    def pause_task(self, task_id: str) -> bool:
        """暂停任务"""
        task = self._tasks.get(task_id)
        if task:
            task.status = "paused"
            logger.info(f"任务已暂停: {task_id}")
            return True
        return False
    
    def resume_task(self, task_id: str) -> bool:
        """恢复任务"""
        task = self._tasks.get(task_id)
        if task:
            task.status = "running"
            logger.info(f"任务已恢复: {task_id}")
            return True
        return False
    
    def stop_task(self, task_id: str) -> bool:
        """停止任务"""
        task = self._tasks.get(task_id)
        if task:
            task.status = "stopped"
            logger.info(f"任务已停止: {task_id}")
            return True
        return False
    
    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        if task_id in self._tasks:
            del self._tasks[task_id]
            logger.info(f"任务已删除: {task_id}")
            return True
        return False
    
    # ============ 执行监控 ============
    
    def execute_task(self, task_id: str) -> List[MatchResult]:
        """
        执行一次监控任务
        
        Returns:
            匹配结果列表
        """
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        
        if task.status == "stopped":
            logger.warning(f"任务已停止，跳过执行: {task_id}")
            return []
        
        logger.info(f"执行任务: {task_id} ({task.name})")
        
        task.last_run_at = datetime.now()
        task.run_count += 1
        
        template = self.template_manager.get_template(task.template_id)
        if not template:
            logger.error(f"模板不存在: {task.template_id}")
            return []
        
        matches = []
        
        # 遍历关键词搜索
        for keyword in task.keywords:
            optimized = self._optimize_keyword(keyword)
            logger.info(f"搜索: {keyword} -> {optimized}")
            
            # 搜索数据源
            contents = self._search_data_sources(optimized, task.data_sources)
            
            # 分析匹配
            for content_item in contents:
                result = self._analyze_content(
                    content=content_item['content'],
                    template=template,
                    task=task
                )
                
                if result.is_match and result.confidence >= task.min_confidence:
                    # 检查是否通过过滤条件
                    if self._pass_filters(result.extracted_fields, task.filters):
                        result.task_id = task_id
                        result.source_id = content_item.get('id', 'unknown')
                        result.source_url = content_item.get('url', '')
                        result.source_content = content_item['content']
                        
                        matches.append(result)
                        task.match_count += 1
                        
                        # 触发回调
                        if task.on_match:
                            try:
                                task.on_match(result.to_dict())
                            except Exception as e:
                                logger.error(f"回调执行失败: {e}")
        
        logger.info(f"任务 {task_id} 执行完成，发现 {len(matches)} 条匹配")
        return matches
    
    def _optimize_keyword(self, keyword: str) -> str:
        """优化关键词"""
        # 简化版：移除常见冗余词
        redundant_words = ['有没有', '有人', '吗', '请问', '最近', '想', '要']
        optimized = keyword
        for word in redundant_words:
            optimized = optimized.replace(word, '')
        return optimized.strip() or keyword
    
    def _search_data_sources(self, keyword: str, sources: List[str]) -> List[dict]:
        """搜索数据源"""
        results = []
        
        for source in sources:
            if source == "xiaohongshu":
                try:
                    feeds = self._search_xiaohongshu(keyword)
                    for feed in feeds:
                        note_card = feed.get('noteCard', feed)
                        results.append({
                            'id': feed.get('id'),
                            'content': note_card.get('displayTitle', ''),
                            'url': f"https://www.xiaohongshu.com/explore/{feed.get('id', '')}",
                            'source': 'xiaohongshu'
                        })
                except Exception as e:
                    logger.error(f"小红书搜索失败: {e}")
        
        return results
    
    def _search_xiaohongshu(self, keyword: str) -> List[dict]:
        """搜索小红书"""
        try:
            # 动态导入避免依赖问题
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from clients.xiaohongshu_mcp import XiaohongshuMCPClient
            
            with XiaohongshuMCPClient(self.mcp_url) as client:
                return client.search_feeds(keyword, sort_by="最新")
        except Exception as e:
            logger.error(f"小红书 MCP 调用失败: {e}")
            return []
    
    def _analyze_content(self, 
                         content: str,
                         template: TaskTemplate,
                         task: MonitoringTask) -> MatchResult:
        """分析内容是否匹配模板"""
        # 构建提示词
        fields_desc = "\n".join([
            f"- {f.name} ({f.label}): {f.ai_extract_prompt or '提取该字段'}"
            for f in template.fields
        ])
        
        prompt = f"""分析以下内容是否符合"{template.name}"的特征。

内容: "{content}"

需要提取的字段：
{fields_desc}

请仔细分析并返回以下 JSON 格式：
{{
    "is_match": true/false,
    "confidence": 0.0-1.0,
    "extracted_fields": {{
        "字段名": "提取的值"
    }},
    "summary": "一句话摘要"
}}

判断标准：
- is_match: 内容是否与"{template.name}"相关
- confidence: 匹配置信度（0-1之间）
- extracted_fields: 尽可能提取所有字段，没有则留空
- summary: 简短描述这条内容是什么"""
        
        try:
            response = self._call_ai(prompt)
            if response:
                # 解析 JSON
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    data = json.loads(json_str)
                    
                    return MatchResult(
                        task_id=task.id,
                        source_id='',
                        source_url='',
                        source_content=content,
                        template_id=template.id,
                        is_match=data.get('is_match', False),
                        confidence=data.get('confidence', 0.0),
                        extracted_fields=data.get('extracted_fields', {}),
                        summary=data.get('summary', '')
                    )
        except Exception as e:
            logger.error(f"AI 分析失败: {e}")
        
        # 返回不匹配结果
        return MatchResult(
            task_id=task.id,
            source_id='',
            source_url='',
            source_content=content,
            template_id=template.id,
            is_match=False,
            confidence=0.0,
            extracted_fields={},
            summary=''
        )
    
    def _pass_filters(self, fields: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """检查是否通过过滤条件"""
        for key, value in filters.items():
            field_value = fields.get(key)
            
            # 精确匹配
            if isinstance(value, (str, int, float, bool)):
                if field_value != value:
                    return False
            
            # 范围匹配（如 price_max, price_min）
            elif key.endswith('_max') and isinstance(value, (int, float)):
                real_key = key[:-4]
                try:
                    if float(field_value or 0) > value:
                        return False
                except:
                    pass
            
            elif key.endswith('_min') and isinstance(value, (int, float)):
                real_key = key[:-4]
                try:
                    if float(field_value or 0) < value:
                        return False
                except:
                    pass
            
            # 包含匹配
            elif key.endswith('_contains') and isinstance(value, str):
                real_key = key[:-9]
                if value.lower() not in str(field_value or '').lower():
                    return False
        
        return True
    
    def _call_ai(self, prompt: str, temperature: float = 0.1) -> Optional[str]:
        """调用 AI 服务"""
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.zhipu_api_key}"
            }
            
            payload = {
                "model": "glm-4-flash",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "stream": False
            }
            
            response = requests.post(
                "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                logger.error(f"AI API 错误: {response.status_code}")
                
        except Exception as e:
            logger.error(f"AI 调用失败: {e}")
        
        return None


# 全局服务实例
_monitor_service = None

def get_monitor_service(zhipu_api_key: str = None, mcp_url: str = None) -> UniversalMonitorService:
    """获取监控服务单例"""
    global _monitor_service
    
    if _monitor_service is None:
        if zhipu_api_key is None:
            zhipu_api_key = os.environ.get('ZHIPU_API_KEY', '')
        if mcp_url is None:
            mcp_url = os.environ.get('MCP_XIAOHONGSHU_URL', 'http://localhost:18060/mcp')
        
        _monitor_service = UniversalMonitorService(
            zhipu_api_key=zhipu_api_key,
            mcp_url=mcp_url
        )
    
    return _monitor_service
