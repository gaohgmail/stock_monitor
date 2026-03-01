# -*- coding: utf-8 -*-
"""
内存缓存管理器
"""

from typing import Optional, Dict, Any
from datetime import datetime


class CacheManager:
    """内存缓存管理器"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._cache: Dict[str, Any] = {}

    def get_key(self, prefix: str, date: datetime, **kwargs) -> str:
        """生成标准化缓存键"""
        date_str = date.strftime('%Y%m%d')
        if kwargs:
            kwargs_str = '_'.join([f"{k}={v}" for k, v in sorted(kwargs.items())])
            return f"{prefix}_{date_str}_{kwargs_str}"
        return f"{prefix}_{date_str}"

    def get(self, key: str) -> Optional[Any]:
        return self._cache.get(key) if self.enabled else None

    def set(self, key: str, value: Any) -> None:
        if self.enabled and value is not None:
            self._cache[key] = value

    def clear(self) -> None:
        self._cache.clear()

    def info(self) -> Dict[str, Any]:
        return {
            'enabled': self.enabled,
            'count': len(self._cache),
            'keys': list(self._cache.keys())
        }

