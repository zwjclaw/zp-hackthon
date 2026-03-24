"""
核心业务服务层
Web 和 Skill 共用同一套业务逻辑
"""

import os
import sys
import json
import logging
import requests
import sseclient
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# 配置日志
def setup_logging(log_file: str = 'log/tickethunter.log', level=logging.INFO):
    """配置日志系统"""
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.handlers.RotatingFileHandler(
                log_file, maxBytes=1024*1024, backupCount=5, encoding='utf-8'
            ),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()


class TicketService:
    """
    票务服务核心类
    提供搜索、分析、监控等所有业务功能
    """
    
    def __init__(self, 
                 zhipu_api_key: str,
                 mcp_url: str = "http://localhost:18060/mcp",
                 db_session=None):
        """
        初始化票务服务
        
        Args:
            zhipu_api_key: 智谱 AI API Key
            mcp_url: 小红书 MCP 服务地址
            db_session: 数据库会话（可选，无数据库时用内存存储）
        """
        self.zhipu_api_key = zhipu_api_key
        self.mcp_url = mcp_url
        self.db_session = db_session
        self.db_lock = Lock()
        
        # 内存存储（无数据库时使用）
        self._memory_notes: Dict[str, dict] = {}
        self._memory_tickets: Dict[int, dict] = {}
        self._memory_tasks: Dict[int, dict] = {}
        self._ticket_id_counter = 1
        self._task_id_counter = 1
        
        logger.info("TicketService 初始化完成")
    
    # ============ 关键词优化 ============
    
    def optimize_keyword(self, original_keyword: str) -> str:
        """
        使用大模型优化搜索关键词
        
        Args:
            original_keyword: 原始关键词
            
        Returns:
            优化后的关键词
        """
        logger.info(f"开始优化关键词: {original_keyword}")
        
        try:
            prompt = self._get_keyword_optimization_prompt(original_keyword)
            
            response = self._call_zhipu_ai(
                prompt=prompt,
                temperature=0.3,
                stream=False
            )
            
            if response:
                optimized = response.strip()
                # 去除可能的引号
                optimized = optimized.strip('"\'')
                logger.info(f"关键词优化: '{original_keyword}' -> '{optimized}'")
                return optimized if optimized else original_keyword
                
        except Exception as e:
            logger.error(f"关键词优化失败: {e}")
            
        return original_keyword
    
    # ============ 票务搜索 ============
    
    def search_tickets(self, 
                       keyword: str,
                       limit: int = 20,
                       optimize: bool = True) -> Dict[str, Any]:
        """
        搜索票务（单次搜索）
        
        Args:
            keyword: 搜索关键词
            limit: 返回结果数量上限
            optimize: 是否优化关键词
            
        Returns:
            {
                'success': bool,
                'keyword': str,
                'optimized_keyword': str,
                'total_notes': int,
                'ticket_count': int,
                'tickets': List[dict]
            }
        """
        logger.info(f"开始搜索票务: {keyword}")
        
        try:
            # 1. 优化关键词
            optimized = self.optimize_keyword(keyword) if optimize else keyword
            
            # 2. 搜索小红书
            feeds = self._search_xiaohongshu(optimized, limit)
            
            # 3. 分析票务信息
            tickets = []
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {
                    executor.submit(self._analyze_note, feed): feed 
                    for feed in feeds
                }
                
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result and result.get('is_ticket'):
                            tickets.append(result['ticket'])
                    except Exception as e:
                        logger.error(f"分析笔记失败: {e}")
            
            logger.info(f"搜索完成: 找到 {len(feeds)} 条笔记, {len(tickets)} 条票务")
            
            return {
                'success': True,
                'keyword': keyword,
                'optimized_keyword': optimized,
                'total_notes': len(feeds),
                'ticket_count': len(tickets),
                'tickets': tickets[:limit]
            }
            
        except Exception as e:
            logger.error(f"搜索票务失败: {e}")
            return {
                'success': False,
                'keyword': keyword,
                'error': str(e),
                'tickets': []
            }
    
    # ============ 监控任务 ============
    
    def start_monitoring(self, 
                         keyword: str,
                         interval_seconds: int = 3600,
                         on_new_ticket: callable = None) -> str:
        """
        启动监控任务
        
        Args:
            keyword: 监控关键词
            interval_seconds: 检查间隔（秒）
            on_new_ticket: 发现新票务时的回调函数
            
        Returns:
            task_id: 任务 ID
        """
        logger.info(f"启动监控任务: {keyword}, 间隔: {interval_seconds}秒")
        
        # 创建任务记录
        task = {
            'id': self._task_id_counter,
            'keyword': keyword,
            'optimized_keyword': self.optimize_keyword(keyword),
            'interval': interval_seconds,
            'status': 'running',
            'created_at': datetime.now(),
            'last_run_at': None,
            'run_count': 0,
            'ticket_count': 0,
            'on_new_ticket': on_new_ticket
        }
        
        self._memory_tasks[task['id']] = task
        self._task_id_counter += 1
        
        logger.info(f"监控任务已创建: {task['id']}")
        return str(task['id'])
    
    def get_task(self, task_id: str) -> Optional[dict]:
        """获取任务信息"""
        return self._memory_tasks.get(int(task_id)) if task_id.isdigit() else None
    
    def list_tasks(self) -> List[dict]:
        """列出所有任务"""
        return list(self._memory_tasks.values())
    
    def stop_task(self, task_id: str) -> bool:
        """停止任务"""
        task = self.get_task(task_id)
        if task:
            task['status'] = 'stopped'
            logger.info(f"任务已停止: {task_id}")
            return True
        return False
    
    def execute_task_once(self, task_id: str) -> Dict[str, Any]:
        """
        执行一次监控任务（用于定时调用）
        
        Args:
            task_id: 任务 ID
            
        Returns:
            执行结果
        """
        task = self.get_task(task_id)
        if not task:
            return {'success': False, 'error': '任务不存在'}
        
        if task['status'] != 'running':
            return {'success': False, 'error': '任务未运行'}
        
        logger.info(f"执行任务: {task_id}, 关键词: {task['optimized_keyword']}")
        
        # 执行搜索
        result = self.search_tickets(
            keyword=task['optimized_keyword'],
            optimize=False  # 已经优化过了
        )
        
        # 更新任务状态
        task['last_run_at'] = datetime.now()
        task['run_count'] += 1
        task['ticket_count'] += result.get('ticket_count', 0)
        
        # 触发回调
        if result['success'] and result['tickets'] and task.get('on_new_ticket'):
            for ticket in result['tickets']:
                try:
                    task['on_new_ticket'](ticket)
                except Exception as e:
                    logger.error(f"回调执行失败: {e}")
        
        return result
    
    # ============ 票务分析 ============
    
    def analyze_ticket(self, note_content: str) -> Dict[str, Any]:
        """
        分析单条笔记是否为票务信息
        
        Args:
            note_content: 笔记内容
            
        Returns:
            {
                'is_ticket': bool,
                'ticket': dict or None,
                'raw_analysis': dict
            }
        """
        result = self._analyze_note({'displayTitle': note_content})
        return {
            'is_ticket': result.get('is_ticket', False),
            'ticket': result.get('ticket'),
            'raw_analysis': result.get('analysis', {})
        }
    
    # ============ 内部方法 ============
    
    def _search_xiaohongshu(self, keyword: str, limit: int = 20) -> List[dict]:
        """调用小红书 MCP 搜索"""
        from clients.xiaohongshu_mcp import XiaohongshuMCPClient
        
        try:
            with XiaohongshuMCPClient(self.mcp_url) as client:
                feeds = client.search_feeds(keyword, sort_by="最新")
                return feeds[:limit] if feeds else []
        except Exception as e:
            logger.error(f"小红书搜索失败: {e}")
            raise
    
    def _analyze_note(self, feed: dict) -> Optional[dict]:
        """分析单条笔记，提取票务信息"""
        try:
            note_card = feed.get('noteCard', feed)  # 兼容两种格式
            content = note_card.get('displayTitle', '')
            note_id = feed.get('id', 'unknown')
            
            if not content:
                return None
            
            # 调用 AI 分析
            analysis = self._analyze_with_ai(content)
            
            if analysis.get('is_ticket_resale'):
                ticket = {
                    'note_id': note_id,
                    'event_name': analysis.get('event_name', ''),
                    'city': analysis.get('city', ''),
                    'event_date': analysis.get('event_date'),
                    'area': analysis.get('area', ''),
                    'price': analysis.get('price', ''),
                    'quantity': analysis.get('quantity', ''),
                    'contact': analysis.get('contact', ''),
                    'notes': analysis.get('notes', ''),
                    'note_url': f"https://www.xiaohongshu.com/explore/{note_id}",
                    'analyzed_at': datetime.now().isoformat()
                }
                
                return {
                    'is_ticket': True,
                    'ticket': ticket,
                    'analysis': analysis
                }
            
            return {'is_ticket': False, 'analysis': analysis}
            
        except Exception as e:
            logger.error(f"分析笔记失败: {e}")
            return None
    
    def _analyze_with_ai(self, content: str) -> dict:
        """使用智谱 AI 分析内容"""
        prompt = self._get_ticket_analysis_prompt(content)
        
        try:
            response = self._call_zhipu_ai(
                prompt=prompt,
                temperature=0.1,
                stream=True
            )
            
            if response:
                # 解析 JSON
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    result = json.loads(json_str)
                    return result
                    
        except Exception as e:
            logger.error(f"AI 分析失败: {e}")
            
        return {'is_ticket_resale': False}
    
    def _call_zhipu_ai(self, 
                       prompt: str, 
                       temperature: float = 0.1,
                       stream: bool = False) -> Optional[str]:
        """调用智谱 AI API"""
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.zhipu_api_key}"
            }
            
            payload = {
                "model": "glm-4-flash",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "stream": stream
            }
            
            response = requests.post(
                "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code != 200:
                logger.error(f"智谱 AI 调用失败: {response.status_code}")
                return None
            
            if stream:
                # 处理流式响应
                full_text = ""
                sse = sseclient.SSEClient(response)
                for event in sse.events():
                    if event.data:
                        try:
                            data = json.loads(event.data)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            if isinstance(delta, dict) and "content" in delta:
                                full_text += delta["content"]
                        except:
                            continue
                return full_text
            else:
                # 非流式响应
                result = response.json()
                return result.get("choices", [{}])[0].get("message", {}).get("content", "")
                
        except Exception as e:
            logger.error(f"调用智谱 AI 失败: {e}")
            return None
    
    def _get_keyword_optimization_prompt(self, keyword: str) -> str:
        """获取关键词优化提示词"""
        return f"""你是一个搜索关键词优化专家。请分析用户输入，提取核心搜索词，去除冗余词汇。

用户输入: "{keyword}"

要求:
1. 只保留核心实体和动作词
2. 去除语气词、时间词、地点修饰词
3. 返回最简洁有效的搜索关键词
4. 直接返回优化后的关键词，不要解释

示例:
输入: "周杰伦演唱会有人转让票吗" 输出: "周杰伦演唱会转让票"
输入: "最近有没有陈奕迅香港的演唱会门票出售" 输出: "陈奕迅香港演唱会门票"
输入: "求购林俊杰北京站门票两张" 输出: "林俊杰北京门票"
"""

    def _get_ticket_analysis_prompt(self, content: str) -> str:
        """获取票务分析提示词"""
        return f"""请分析以下内容是否为演出/活动票务转让信息。

内容: "{content}"

如果是票务转让信息，请以 JSON 格式返回以下字段：
{{
    "is_ticket_resale": true,
    "event_name": "演出/活动名称",
    "city": "城市",
    "event_date": "日期(YYYY-MM-DD格式，不确定则为null)",
    "area": "座位区域/票价档位",
    "price": "转让价格",
    "quantity": "票数",
    "contact": "联系方式(手机号/微信等，脱敏处理)",
    "notes": "其他备注"
}}

如果不是票务转让信息，返回：
{{"is_ticket_resale": false}}

注意:
1. 只返回 JSON，不要其他解释
2. 不确定的字段可以留空或设为 null
3. 联系方式请做脱敏处理(如 138****8888)"""


# 全局服务实例（单例模式）
_ticket_service: Optional[TicketService] = None

def get_ticket_service(zhipu_api_key: str = None, 
                       mcp_url: str = None) -> TicketService:
    """
    获取 TicketService 单例实例
    
    Args:
        zhipu_api_key: 智谱 AI API Key
        mcp_url: 小红书 MCP 服务地址
        
    Returns:
        TicketService 实例
    """
    global _ticket_service
    
    if _ticket_service is None:
        # 从环境变量或配置文件读取
        if zhipu_api_key is None:
            zhipu_api_key = os.environ.get('ZHIPU_API_KEY', '')
        if mcp_url is None:
            mcp_url = os.environ.get('MCP_XIAOHONGSHU_URL', 'http://localhost:18060/mcp')
            
        _ticket_service = TicketService(
            zhipu_api_key=zhipu_api_key,
            mcp_url=mcp_url
        )
    
    return _ticket_service
