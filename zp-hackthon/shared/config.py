"""
共享配置
"""

import os


class Config:
    """基础配置"""
    
    # 基础配置
    DEBUG = False
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_key')
    
    # 数据库配置
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///tickethunter.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 智谱 AI 配置
    ZHIPU_API_KEY = os.environ.get('ZHIPU_API_KEY', '')
    
    # 小红书 MCP 服务配置
    MCP_XIAOHONGSHU_URL = os.environ.get('MCP_XIAOHONGSHU_URL', 'http://localhost:18060/mcp')
    
    # 监控配置
    MONITOR_INTERVAL = int(os.environ.get('MONITOR_INTERVAL', '300'))  # 5分钟
    
    # 缓存配置
    CACHE_TYPE = 'simple'
    CACHE_DEFAULT_TIMEOUT = 300
    
    # 限流配置
    RATELIMIT_DEFAULT = "200 per day;50 per hour"
    RATELIMIT_STORAGE_URL = "memory://"
    
    # 日志配置
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', 'log/tickethunter.log')


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///tickethunter_dev.db'


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False
    LOG_LEVEL = 'WARNING'
    MONITOR_INTERVAL = 600  # 10分钟


# 配置映射
config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': Config
}


def get_config(env: str = None):
    """获取配置类"""
    if env is None:
        env = os.environ.get('FLASK_ENV', 'default')
    return config_map.get(env, Config)
