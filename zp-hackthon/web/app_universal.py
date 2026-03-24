"""
通用监控平台 Web 层
支持多模板、动态表单、多数据源
"""

import os
import sys
import json
from datetime import datetime
from queue import Queue, Empty

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from shared.config import get_config
from services.universal_monitor import get_monitor_service
from models.database import db, init_app as init_db, save_template, save_task, save_match_result

# 创建扩展对象
cache = Cache()
limiter = Limiter(key_func=get_remote_address)

# 事件队列（用于 SSE）
event_queue = Queue()


def create_app(config_name=None):
    """创建 Flask 应用"""
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static'
    )
    
    # 加载配置
    config = get_config(config_name)
    app.config.from_object(config)
    
    # 初始化扩展
    db.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)
    
    # 初始化数据库
    with app.app_context():
        db.create_all()
        # 初始化预置模板
        _init_builtin_templates()
    
    # 注册路由
    register_routes(app)
    
    return app


def _init_builtin_templates():
    """初始化预置模板到数据库"""
    from services.universal_monitor import BUILTIN_TEMPLATES
    
    for template_id, template in BUILTIN_TEMPLATES.items():
        template_data = template.to_dict()
        template_data['is_builtin'] = True
        save_template(template_data)
    
    print(f"已初始化 {len(BUILTIN_TEMPLATES)} 个预置模板")


def register_routes(app):
    """注册路由"""
    monitor_service = get_monitor_service(
        zhipu_api_key=app.config.get('ZHIPU_API_KEY', ''),
        mcp_url=app.config.get('MCP_XIAOHONGSHU_URL', 'http://localhost:18060/mcp')
    )
    
    # ========== 页面路由 ==========
    
    @app.route('/')
    def index():
        """首页 - 动态渲染模板选择"""
        templates = monitor_service.list_templates()
        return render_template('index_universal.html', templates=templates)
    
    @app.route('/templates')
    def templates_page():
        """模板管理页面"""
        templates = monitor_service.list_templates()
        return render_template('templates.html', templates=templates)
    
    @app.route('/tasks')
    def tasks_page():
        """任务管理页面"""
        return render_template('tasks.html')
    
    @app.route('/create')
    def create_task_page():
        """创建任务页面"""
        template_id = request.args.get('template', 'ticket')
        template = monitor_service.get_template(template_id)
        templates = monitor_service.list_templates()
        return render_template('create_task.html', 
                             template=template.to_dict() if template else None,
                             templates=templates,
                             selected_template=template_id)
    
    # ========== API 路由 - 模板 ==========
    
    @app.route('/api/templates', methods=['GET'])
    @cache.cached(timeout=60)
    def api_list_templates():
        """列出所有模板"""
        category = request.args.get('category')
        templates = monitor_service.list_templates(category)
        return jsonify({
            'success': True,
            'data': templates
        })
    
    @app.route('/api/templates/<template_id>', methods=['GET'])
    def api_get_template(template_id):
        """获取模板详情"""
        template = monitor_service.get_template(template_id)
        if template:
            return jsonify({
                'success': True,
                'data': template.to_dict()
            })
        return jsonify({'success': False, 'error': '模板不存在'}), 404
    
    @app.route('/api/templates', methods=['POST'])
    @limiter.limit("10 per minute")
    def api_create_template():
        """创建自定义模板"""
        data = request.get_json()
        
        try:
            template = monitor_service.create_custom_template(
                name=data['name'],
                description=data.get('description', ''),
                category=data.get('category', '其他'),
                fields=data.get('fields', []),
                icon=data.get('icon', '📝')
            )
            
            # 保存到数据库
            save_template(template.to_dict())
            
            return jsonify({
                'success': True,
                'data': template.to_dict()
            })
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 400
    
    # ========== API 路由 - 任务 ==========
    
    @app.route('/api/tasks', methods=['GET'])
    def api_list_tasks():
        """列出所有任务"""
        status = request.args.get('status')
        tasks = monitor_service.list_tasks(status)
        return jsonify({
            'success': True,
            'data': tasks
        })
    
    @app.route('/api/tasks', methods=['POST'])
    @limiter.limit("10 per minute")
    def api_create_task():
        """创建任务"""
        data = request.get_json()
        
        try:
            def on_match(result):
                """匹配回调 - 推送 SSE"""
                from models.database import MatchResultDB
                # 保存到数据库
                save_match_result(result)
                # 推送事件
                event_queue.put({
                    'type': 'match',
                    'data': result
                })
            
            task = monitor_service.create_task(
                name=data['name'],
                template_id=data['template_id'],
                keywords=data['keywords'],
                filters=data.get('filters', {}),
                interval_minutes=data.get('interval_minutes', 60),
                min_confidence=data.get('min_confidence', 0.7),
                on_match=on_match
            )
            
            # 保存到数据库
            save_task(task.to_dict())
            
            return jsonify({
                'success': True,
                'data': task.to_dict()
            })
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 400
    
    @app.route('/api/tasks/<task_id>', methods=['GET'])
    def api_get_task(task_id):
        """获取任务详情"""
        task = monitor_service.get_task(task_id)
        if task:
            return jsonify({
                'success': True,
                'data': task.to_dict()
            })
        return jsonify({'success': False, 'error': '任务不存在'}), 404
    
    @app.route('/api/tasks/<task_id>/execute', methods=['POST'])
    def api_execute_task(task_id):
        """立即执行任务"""
        try:
            matches = monitor_service.execute_task(task_id)
            
            # 保存结果到数据库
            for match in matches:
                save_match_result(match.to_dict())
            
            return jsonify({
                'success': True,
                'data': [m.to_dict() for m in matches]
            })
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 400
    
    @app.route('/api/tasks/<task_id>/stop', methods=['POST'])
    def api_stop_task(task_id):
        """停止任务"""
        if monitor_service.stop_task(task_id):
            # 更新数据库
            from models.database import MonitoringTaskDB
            task_db = MonitoringTaskDB.query.get(task_id)
            if task_db:
                task_db.status = 'stopped'
                db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': '任务不存在'}), 404
    
    @app.route('/api/tasks/<task_id>/pause', methods=['POST'])
    def api_pause_task(task_id):
        """暂停任务"""
        if monitor_service.pause_task(task_id):
            from models.database import MonitoringTaskDB
            task_db = MonitoringTaskDB.query.get(task_id)
            if task_db:
                task_db.status = 'paused'
                db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': '任务不存在'}), 404
    
    @app.route('/api/tasks/<task_id>/resume', methods=['POST'])
    def api_resume_task(task_id):
        """恢复任务"""
        if monitor_service.resume_task(task_id):
            from models.database import MonitoringTaskDB
            task_db = MonitoringTaskDB.query.get(task_id)
            if task_db:
                task_db.status = 'running'
                db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': '任务不存在'}), 404
    
    @app.route('/api/tasks/<task_id>', methods=['DELETE'])
    def api_delete_task(task_id):
        """删除任务"""
        if monitor_service.delete_task(task_id):
            from models.database import MonitoringTaskDB
            task_db = MonitoringTaskDB.query.get(task_id)
            if task_db:
                db.session.delete(task_db)
                db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': '任务不存在'}), 404
    
    # ========== API 路由 - 结果 ==========
    
    @app.route('/api/results', methods=['GET'])
    def api_list_results():
        """列出匹配结果"""
        task_id = request.args.get('task_id')
        is_notified = request.args.get('is_notified')
        
        from models.database import MatchResultDB
        
        query = MatchResultDB.query
        if task_id:
            query = query.filter_by(task_id=task_id)
        if is_notified is not None:
            query = query.filter_by(is_notified=is_notified.lower() == 'true')
        
        results = query.order_by(MatchResultDB.created_at.desc()).limit(100).all()
        
        return jsonify({
            'success': True,
            'data': [r.to_dict() for r in results]
        })
    
    @app.route('/api/results/<int:result_id>/notify', methods=['POST'])
    def api_mark_notified(result_id):
        """标记结果已通知"""
        from models.database import MatchResultDB
        result = MatchResultDB.query.get(result_id)
        if result:
            result.is_notified = True
            result.notification_sent_at = datetime.utcnow()
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': '结果不存在'}), 404
    
    # ========== API 路由 - 分析 ==========
    
    @app.route('/api/analyze', methods=['POST'])
    @limiter.limit("30 per minute")
    def api_analyze():
        """分析内容"""
        data = request.get_json()
        content = data.get('content', '')
        template_id = data.get('template_id', 'ticket')
        
        try:
            template = monitor_service.get_template(template_id)
            if not template:
                return jsonify({'success': False, 'error': '模板不存在'}), 404
            
            # 创建临时任务分析
            from services.universal_monitor import MonitoringTask
            temp_task = MonitoringTask(
                id="temp",
                name="temp",
                template_id=template_id,
                keywords=[],
                min_confidence=0.0
            )
            
            result = monitor_service._analyze_content(content, template, temp_task)
            
            return jsonify({
                'success': True,
                'data': {
                    'is_match': result.is_match,
                    'confidence': result.confidence,
                    'extracted_fields': result.extracted_fields,
                    'summary': result.summary
                }
            })
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 400
    
    # ========== SSE 实时推送 ==========
    
    @app.route('/api/stream')
    def api_stream():
        """SSE 实时推送"""
        def event_stream():
            try:
                while True:
                    try:
                        message = event_queue.get(timeout=30)
                        if message:
                            yield f"data: {json.dumps(message)}\n\n"
                    except Empty:
                        yield ": heartbeat\n\n"
            except GeneratorExit:
                pass
            except Exception as e:
                print(f"SSE 错误: {e}")
        
        return Response(
            stream_with_context(event_stream()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no'
            }
        )


# 创建应用实例
app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=app.config.get('DEBUG', False))
