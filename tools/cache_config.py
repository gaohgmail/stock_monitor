# -*- coding: utf-8 -*-
# tools/cache_config.py

import functools
import sys
from typing import Callable, Any

# ==================== 1. 环境检测 ====================
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    st = None
    HAS_STREAMLIT = False

# ==================== 2. 缓存策略配置 (TTL) ====================
# 单位：秒
CACHE_TTL = {
    'short': 60,        # 1分钟：高频变化数据 (如实时计算结果)
    'medium': 300,      # 5分钟：一般性分析结果
    'long': 3600,       # 1小时：相对稳定的数据
    'daily': 86400,     # 24小时：历史日线数据、日历等
}

# ==================== 3. 缓存装饰器 ====================

def cached_data(ttl_seconds: int = CACHE_TTL['medium'], show_spinner: bool = False):
    """
    轻量级缓存装饰器，兼容 Streamlit 和 普通 Python 脚本环境。
    
    参数:
        ttl_seconds: 缓存过期时间 (秒)
        show_spinner: 是否显示 Streamlit 加载转圈 (仅在 Streamlit 下有效)
    """
    def decorator(func: Callable) -> Callable:
        
        # 场景 A: Streamlit 环境 -> 使用 st.cache_data
        if HAS_STREAMLIT:
            return st.cache_data(ttl=ttl_seconds, show_spinner=show_spinner)(func)
        
        # 场景 B: 普通脚本环境 (如 main.py) -> 直接执行，不缓存
        # (也可以在这里接入 joblib/functools.lru_cache，但为了脚本稳定性，
        # 通常脚本一次性运行不需要复杂缓存，直接透传即可)
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            return func(*args, **kwargs)
            
        return wrapper
        
    return decorator


def cached_resource():
    """
    资源单例装饰器，确保资源在整个应用生命周期内只创建一次。
    适用于调度器、数据库连接等需要单例模式的资源。
    """
    def decorator(func: Callable) -> Callable:
        cache_key = f"_cached_resource_{func.__name__}"
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # 在 Streamlit 环境中使用 session_state 存储单例
            if HAS_STREAMLIT:
                if cache_key not in st.session_state:
                    st.session_state[cache_key] = func(*args, **kwargs)
                return st.session_state[cache_key]
            else:
                # 普通脚本环境：使用函数属性存储
                if not hasattr(wrapper, '_instance'):
                    wrapper._instance = func(*args, **kwargs)
                return wrapper._instance
                
        return wrapper
    return decorator
