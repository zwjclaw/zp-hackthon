#!/usr/bin/env python3
"""
TicketHunter 结构验证测试
不依赖外部包，只验证代码结构和语法
"""

import ast
import sys
import os

os.chdir('/home/node/.openclaw/workspace/zp-hackthon/zp-hackthon')

print("=" * 60)
print("TicketHunter 重构 - 结构验证测试")
print("=" * 60)

def check_syntax(filepath, name):
    """检查 Python 文件语法"""
    print(f"\n[测试] {name}: {filepath}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        ast.parse(code)
        print(f"  ✅ 语法正确 ({len(code)} 字符)")
        return True
    except SyntaxError as e:
        print(f"  ❌ 语法错误: {e}")
        return False
    except Exception as e:
        print(f"  ⚠️  读取错误: {e}")
        return False

# 测试文件列表
files_to_test = [
    ("services/ticket_service.py", "核心 Service 层"),
    ("services/__init__.py", "Service 包"),
    ("clients/xiaohongshu_mcp.py", "MCP 客户端"),
    ("clients/__init__.py", "Client 包"),
    ("skill/tools.py", "Skill 工具"),
    ("skill/__init__.py", "Skill 包"),
    ("shared/config.py", "共享配置"),
    ("shared/__init__.py", "Shared 包"),
    ("web/app.py", "Web 应用"),
    ("web/__init__.py", "Web 包"),
    ("database.py", "数据库模型"),
]

results = []
for filepath, name in files_to_test:
    results.append(check_syntax(filepath, name))

print("\n" + "=" * 60)
if all(results):
    print("✅ 所有文件语法检查通过")
    print("=" * 60)
    print("\n目录结构验证:")
    
    # 验证目录结构
    dirs = ["services", "clients", "skill", "shared", "web", "web/templates"]
    for d in dirs:
        if os.path.isdir(d):
            print(f"  ✅ {d}/")
        else:
            print(f"  ❌ {d}/ 不存在")
    
    print("\n关键文件验证:")
    files = [
        "SKILL.md",
        "REFACTOR.md", 
        ".env.example",
        "requirements.txt",
        "web/templates/index.html"
    ]
    for f in files:
        if os.path.exists(f):
            print(f"  ✅ {f}")
        else:
            print(f"  ❌ {f} 不存在")
    
    print("\n" + "=" * 60)
    print("结构验证完成 ✅")
    print("=" * 60)
    print("\n下一步:")
    print("1. 安装依赖: pip install -r requirements.txt")
    print("2. 配置环境变量: cp .env.example .env && 编辑 .env")
    print("3. 启动 Web: python web/app.py")
    print("4. 测试 Skill: python -c 'from skill.tools import search_tickets'")
    
else:
    print("❌ 部分文件存在语法错误")
    print("=" * 60)
    sys.exit(1)
