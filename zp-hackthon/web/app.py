"""
TicketHunter Web 层
使用 Service 层处理业务逻辑
"""

import os
import sys
import json
from datetime import datetime
from queue import Queue, Empty
from threading import Lock

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config import get_config
from services.ticket_service import get_ticket_service, setup_logging
from database import db, Note, Ticket, WorkflowExecution, init_db

# 配置日志
logger = setup_logging()

# 创建扩展对象
cache = Cache()
limiter = Limiter(key_func=get_remote_address)

# 事件队列（用于 SSE）
event_queue = Queue()
event_lock = Lock()


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
    
    # 确保日志目录存在
    os.makedirs('log', exist_ok=True)
    
    # 初始化扩展
    db.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)
    
    # 初始化服务
    with app.app_context():
        ticket_service = get_ticket_service(
            zhipu_api_key=app.config['ZHIPU_API_KEY'],
            mcp_url=app.config['MCP_XIAOHONGSHU_URL']
        )
        init_db()
    
    # 注册路由
    register_routes(app, ticket_service)
    
    return app


def register_routes(app, ticket_service):
    """注册路由"""
    
    @app.route('/')
    def index():
        """首页"""
        recent_tickets = Ticket.query.order_by(Ticket.created_at.desc()).limit(10).all()
        return render_template('index.html', tickets=recent_tickets)
    
    @app.route('/api/search', methods=['POST'])
    @limiter.limit("10 per minute")
    def api_search():
        """搜索 API"""
        data = request.get_json() or request.form
        keyword = data.get('keyword', '')
        limit = int(data.get('limit', 10))
        
        if not keyword:
            return jsonify({'success': False, 'error': '关键词不能为空'})
        
        try:
            result = ticket_service.search_tickets(keyword, limit=limit)
            
            # 保存到数据库
            if result['success']:
                # 创建任务记录
                task = WorkflowExecution(
                    msg=keyword,
                    status='completed',
                    is_scheduled=False
                )
                db.session.add(task)
                
                # 保存票务
                for ticket_data in result['tickets']:
                    _save_ticket_to_db(ticket_data)
                
                db.session.commit()
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    @app.route('/api/tickets', methods=['GET'])
    @cache.cached(timeout=60)
    def get_tickets():
        """获取票务列表"""
        try:
            tickets = Ticket.query.order_by(Ticket.created_at.desc()).limit(50).all()
            return jsonify([{
                'id': t.id,
                'event_name': t.event_name,
                'city': t.city,
                'event_date': t.event_date.strftime('%Y-%m-%d') if t.event_date else None,
                'area': t.area,
                'price': t.price,
                'quantity': t.quantity,
                'contact': t.contact,
                'notes': t.notes,
                'note_url': t.note.note_url if t.note else None,
                'created_at': t.created_at.strftime('%Y-%m-%d %H:%M:%S')
            } for t in tickets])
        except Exception as e:
            logger.error(f"获取票务列表失败: {e}")
            return jsonify([])
    
    @app.route('/api/monitor/start', methods=['POST'])
    def start_monitor():
        """启动监控任务"""
        data = request.get_json() or request.form
        keyword = data.get('keyword', '')
        interval = int(data.get('interval', 60))  # 默认 60 分钟
        
        if not keyword:
            return jsonify({'success': False, 'error': '关键词不能为空'})
        
        try:
            def on_new_ticket(ticket):
                """新票务回调 - 通过 SSE 推送"""
                with event_lock:
                    event_queue.put({
                        'type': 'new_ticket',
                        'data': ticket,
                        'timestamp': datetime.now().isoformat()
                    })
            
            task_id = ticket_service.start_monitoring(
                keyword=keyword,
                interval_seconds=interval * 60,
                on_new_ticket=on_new_ticket
            )
            
            return jsonify({
                'success': True,
                'task_id': task_id,
                'message': f'监控任务已启动: {keyword}'
            })
            
        except Exception as e:
            logger.error(f"启动监控失败: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    @app.route('/api/tasks', methods=['GET'])
    def get_tasks():
        """获取任务列表"""
        try:
            tasks = ticket_service.list_tasks()
            return jsonify([{
                'id': t['id'],
                'keyword': t['optimized_keyword'],
                'status': t['status'],
                'interval': t['interval'],
                'run_count': t['run_count'],
                'ticket_count': t['ticket_count'],
                'created_at': t['created_at'].isoformat()
            } for t in tasks])
        except Exception as e:
            logger.error(f"获取任务列表失败: {e}")
            return jsonify([])
    
    @app.route('/api/tasks/<task_id>/stop', methods=['POST'])
    def stop_task(task_id):
        """停止任务"""
        try:
            if ticket_service.stop_task(task_id):
                return jsonify({'success': True, 'message': '任务已停止'})
            return jsonify({'success': False, 'error': '任务不存在'})
        except Exception as e:
            logger.error(f"停止任务失败: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    @app.route('/api/tasks/<task_id>/execute', methods=['POST'])
    def execute_task(task_id):
        """立即执行一次任务"""
        try:
            result = ticket_service.execute_task_once(task_id)
            return jsonify(result)
        except Exception as e:
            logger.error(f"执行任务失败: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    @app.route('/api/stream')
    def stream():
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
                logger.info("客户端断开连接")
            except Exception as e:
                logger.error(f"SSE 错误: {e}")
        
        return Response(
            stream_with_context(event_stream()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no'
            }
        )


def _save_ticket_to_db(ticket_data: dict):
    """保存票务到数据库"""
    try:
        note_id = ticket_data.get('note_id', 'unknown')
        
        # 检查是否已存在
        existing = Ticket.query.filter_by(note_id=note_id).first()
        if existing:
            return
        
        # 创建笔记记录
        note = Note(
            note_id=note_id,
            description=ticket_data.get('event_name', ''),
            note_url=ticket_data.get('note_url', ''),
            create_time=datetime.now()
        )
        db.session.add(note)
        
        # 创建票务记录
        from datetime import date
        event_date = None
        if ticket_data.get('event_date'):
            try:
                event_date = datetime.strptime(ticket_data['event_date'], '%Y-%m-%d').date()
            except:
                pass
        
        ticket = Ticket(
            note_id=note_id,
            is_ticket_resale=True,
            event_name=ticket_data.get('event_name', ''),
            city=ticket_data.get('city', ''),
            event_date=event_date,
            area=ticket_data.get('area', ''),
            price=ticket_data.get('price', ''),
            quantity=ticket_data.get('quantity', ''),
            contact=ticket_data.get('contact', ''),
            notes=ticket_data.get('notes', '')
        )
        db.session.add(ticket)
        
    except Exception as e:
        logger.error(f"保存票务到数据库失败: {e}")
        db.session.rollback()


# 创建应用实例
app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=app.config.get('DEBUG', False))
