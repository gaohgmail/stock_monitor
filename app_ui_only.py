# -*- coding: utf-8 -*-
"""
量化复盘系统 - UI 启动器
只启动 Streamlit UI，不启动调度器

使用示例:
    python app_ui_only.py
"""

import sys
import subprocess
from datetime import datetime


def start_ui():
    """启动 Streamlit UI（阻塞模式）"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🌐 正在启动 Streamlit UI...")
    try:
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", "ui/ui_main.py"],
            check=False
        )
        return True
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Streamlit 启动失败: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 量化复盘系统 - UI 启动器")
    print("=" * 60)
    print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    print("🌐 Streamlit UI: 启动中...")
    print("-" * 60)
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    
    start_ui()
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🛑 Streamlit UI 已关闭")
    print("=" * 60)
