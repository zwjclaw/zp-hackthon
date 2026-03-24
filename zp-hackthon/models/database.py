"""
数据库模型 - 支持通用监控平台
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()


def init_app(app):
    """初始化数据库应用"""
    db.init_app(app)
    with app.app_context():
        db.create_all()


class Template(db.Model):
    """监控模板表"""
    __tablename__ = 'templates'
    
    id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))
    icon = db.Column(db.String(10), default='📝')
    
    # 字段定义（JSON存储）
    fields_json = db.Column(db.Text)
    
    # AI 配置
    ai_analysis_prompt = db.Column(db.Text)
    is_match_prompt = db.Column(db.Text)
    
    # 数据源配置
    default_data_sources = db.Column(db.Text, default='["xiaohongshu"]')
    
    # 通知规则（JSON存储）
    notification_rules_json = db.Column(db.Text)
    
    # 元数据
    is_builtin = db.Column(db.Boolean, default=False)  # 是否预置模板
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联任务
    tasks = db.relationship('MonitoringTaskDB', backref='template', lazy=True)
    
    def get_fields(self):
        """获取字段定义"""
        if self.fields_json:
            return json.loads(self.fields_json)
        return []
    
    def set_fields(self, fields):
        """设置字段定义"""
        self.fields_json = json.dumps(fields, ensure_ascii=False)
    
    def get_data_sources(self):
        """获取数据源"""
        if self.default_data_sources:
            return json.loads(self.default_data_sources)
        return ["xiaohongshu"]
    
    def set_data_sources(self, sources):
        """设置数据源"""
        self.default_data_sources = json.dumps(sources)
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'icon': self.icon,
            'fields': self.get_fields(),
            'ai_analysis_prompt': self.ai_analysis_prompt,
            'is_match_prompt': self.is_match_prompt,
            'default_data_sources': self.get_data_sources(),
            'notification_rules': json.loads(self.notification_rules_json) if self.notification_rules_json else {},
            'is_builtin': self.is_builtin,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class MonitoringTaskDB(db.Model):
    """监控任务表"""
    __tablename__ = 'monitoring_tasks'
    
    id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    
    # 关联模板
    template_id = db.Column(db.String(50), db.ForeignKey('templates.id'), nullable=False)
    
    # 监控配置
    keywords_json = db.Column(db.Text)  # 关键词列表
    filters_json = db.Column(db.Text)   # 过滤条件
    min_confidence = db.Column(db.Float, default=0.7)
    
    # 数据源
    data_sources_json = db.Column(db.Text)
    
    # 监控间隔（秒）
    interval_seconds = db.Column(db.Integer, default=3600)
    
    # 状态
    status = db.Column(db.String(20), default='running')  # running, paused, stopped
    
    # 统计
    run_count = db.Column(db.Integer, default=0)
    match_count = db.Column(db.Integer, default=0)
    
    # 时间
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_run_at = db.Column(db.DateTime)
    
    # 关联结果
    results = db.relationship('MatchResultDB', backref='task', lazy=True, cascade='all, delete-orphan')
    
    def get_keywords(self):
        """获取关键词"""
        if self.keywords_json:
            return json.loads(self.keywords_json)
        return []
    
    def set_keywords(self, keywords):
        """设置关键词"""
        self.keywords_json = json.dumps(keywords, ensure_ascii=False)
    
    def get_filters(self):
        """获取过滤条件"""
        if self.filters_json:
            return json.loads(self.filters_json)
        return {}
    
    def set_filters(self, filters):
        """设置过滤条件"""
        self.filters_json = json.dumps(filters, ensure_ascii=False)
    
    def get_data_sources(self):
        """获取数据源"""
        if self.data_sources_json:
            return json.loads(self.data_sources_json)
        return []
    
    def set_data_sources(self, sources):
        """设置数据源"""
        self.data_sources_json = json.dumps(sources)
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'template_id': self.template_id,
            'keywords': self.get_keywords(),
            'filters': self.get_filters(),
            'min_confidence': self.min_confidence,
            'data_sources': self.get_data_sources(),
            'interval_seconds': self.interval_seconds,
            'status': self.status,
            'run_count': self.run_count,
            'match_count': self.match_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_run_at': self.last_run_at.isoformat() if self.last_run_at else None
        }


class MatchResultDB(db.Model):
    """匹配结果表"""
    __tablename__ = 'match_results'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # 关联任务
    task_id = db.Column(db.String(50), db.ForeignKey('monitoring_tasks.id'), nullable=False)
    
    # 来源信息
    source_id = db.Column(db.String(100))      # 数据源ID（如小红书note_id）
    source_url = db.Column(db.String(500))     # 来源链接
    source_content = db.Column(db.Text)        # 原始内容
    source_platform = db.Column(db.String(50)) # 平台（xiaohongshu/weibo等）
    
    # 匹配结果
    is_match = db.Column(db.Boolean, default=False)
    confidence = db.Column(db.Float, default=0.0)
    extracted_fields_json = db.Column(db.Text)  # 提取的字段
    summary = db.Column(db.Text)
    
    # 是否已通知
    is_notified = db.Column(db.Boolean, default=False)
    notification_sent_at = db.Column(db.DateTime)
    
    # 时间
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_extracted_fields(self):
        """获取提取的字段"""
        if self.extracted_fields_json:
            return json.loads(self.extracted_fields_json)
        return {}
    
    def set_extracted_fields(self, fields):
        """设置提取的字段"""
        self.extracted_fields_json = json.dumps(fields, ensure_ascii=False)
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'task_id': self.task_id,
            'source_id': self.source_id,
            'source_url': self.source_url,
            'source_content': self.source_content[:200] + '...' if self.source_content and len(self.source_content) > 200 else self.source_content,
            'source_platform': self.source_platform,
            'is_match': self.is_match,
            'confidence': self.confidence,
            'extracted_fields': self.get_extracted_fields(),
            'summary': self.summary,
            'is_notified': self.is_notified,
            'notification_sent_at': self.notification_sent_at.isoformat() if self.notification_sent_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# 兼容旧表（保留原有票务数据）
class Note(db.Model):
    """社交媒体笔记表（旧）"""
    __tablename__ = 'notes'
    
    note_id = db.Column(db.String(50), primary_key=True)
    description = db.Column(db.Text)
    note_url = db.Column(db.String(255))
    create_time = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关联票务信息
    tickets = db.relationship('Ticket', backref='note', lazy=True)


class Ticket(db.Model):
    """票务信息表（旧）"""
    __tablename__ = 'tickets'
    
    id = db.Column(db.Integer, primary_key=True)
    note_id = db.Column(db.String(50), db.ForeignKey('notes.note_id'))
    is_ticket_resale = db.Column(db.Boolean, default=True)
    event_name = db.Column(db.String(100))
    city = db.Column(db.String(50))
    event_date = db.Column(db.Date)
    area = db.Column(db.String(50))
    price = db.Column(db.String(100))
    quantity = db.Column(db.String(50))
    contact = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WorkflowExecution(db.Model):
    """工作流执行记录表（旧）"""
    __tablename__ = 'workflow_executions'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.Integer)
    cost = db.Column(db.String(50))
    msg = db.Column(db.Text)
    status = db.Column(db.String(20), default='running')
    raw_response = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    message = db.Column(db.String(255))
    
    # 定时任务相关字段
    is_scheduled = db.Column(db.Boolean, default=True)
    schedule_interval = db.Column(db.Integer, default=60)
    last_run_at = db.Column(db.DateTime)
    next_run_at = db.Column(db.DateTime)
    run_count = db.Column(db.Integer, default=0)


def init_db():
    """初始化数据库表"""
    db.create_all()


def save_template(template_data: dict) -> Template:
    """保存模板"""
    template = Template.query.get(template_data['id'])
    
    if template:
        # 更新
        template.name = template_data.get('name', template.name)
        template.description = template_data.get('description', template.description)
        template.category = template_data.get('category', template.category)
        template.icon = template_data.get('icon', template.icon)
        template.set_fields(template_data.get('fields', []))
        template.ai_analysis_prompt = template_data.get('ai_analysis_prompt')
        template.is_match_prompt = template_data.get('is_match_prompt')
        template.set_data_sources(template_data.get('default_data_sources', ['xiaohongshu']))
    else:
        # 创建
        template = Template(
            id=template_data['id'],
            name=template_data['name'],
            description=template_data.get('description', ''),
            category=template_data.get('category', '其他'),
            icon=template_data.get('icon', '📝'),
            ai_analysis_prompt=template_data.get('ai_analysis_prompt'),
            is_match_prompt=template_data.get('is_match_prompt'),
            is_builtin=template_data.get('is_builtin', False),
            is_active=True
        )
        template.set_fields(template_data.get('fields', []))
        template.set_data_sources(template_data.get('default_data_sources', ['xiaohongshu']))
        db.session.add(template)
    
    db.session.commit()
    return template


def save_task(task_data: dict) -> MonitoringTaskDB:
    """保存任务"""
    task = MonitoringTaskDB.query.get(task_data['id'])
    
    if task:
        # 更新
        task.name = task_data.get('name', task.name)
        task.status = task_data.get('status', task.status)
        task.run_count = task_data.get('run_count', task.run_count)
        task.match_count = task_data.get('match_count', task.match_count)
        if task_data.get('last_run_at'):
            task.last_run_at = task_data['last_run_at']
    else:
        # 创建
        task = MonitoringTaskDB(
            id=task_data['id'],
            name=task_data['name'],
            template_id=task_data['template_id'],
            min_confidence=task_data.get('min_confidence', 0.7),
            interval_seconds=task_data.get('interval_seconds', 3600),
            status=task_data.get('status', 'running')
        )
        task.set_keywords(task_data.get('keywords', []))
        task.set_filters(task_data.get('filters', {}))
        task.set_data_sources(task_data.get('data_sources', []))
        db.session.add(task)
    
    db.session.commit()
    return task


def save_match_result(result_data: dict) -> MatchResultDB:
    """保存匹配结果"""
    result = MatchResultDB(
        task_id=result_data['task_id'],
        source_id=result_data.get('source_id'),
        source_url=result_data.get('source_url'),
        source_content=result_data.get('source_content'),
        source_platform=result_data.get('source_platform', 'xiaohongshu'),
        is_match=result_data.get('is_match', False),
        confidence=result_data.get('confidence', 0.0),
        summary=result_data.get('summary', '')
    )
    result.set_extracted_fields(result_data.get('extracted_fields', {}))
    
    db.session.add(result)
    db.session.commit()
    return result
