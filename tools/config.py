# -*- coding: utf-8 -*-
# tools/config.py

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Set, Any
from types import MappingProxyType

# ==================== 1. 基础路径架构 (Infrastructure) ====================
# 获取项目根目录 (假设当前文件在 tools/ 下，向上回溯两级)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 确保项目根目录在 sys.path 中，解决模块导入痛点
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 定义核心目录结构
DATA_DIR = PROJECT_ROOT / 'data' / 'raw'          # 原始数据
METADATA_DIR = PROJECT_ROOT / 'metadata'          # 元数据、配置、状态
SAVE_DIR = PROJECT_ROOT / 'analysis_results'      # 分析结果输出
MARKET_REPORT_DIR = SAVE_DIR / 'market_daily'     # 每日市场报表

# 新增：分类存储目录
LIMIT_UP_DIR = SAVE_DIR / 'limit_up'              # 涨停数据（竞价/收盘）
CONCEPT_DIR = SAVE_DIR / 'concept'                # 题材概念数据

# 同花顺数据下载目录
THS_DATA_ROOT = DATA_DIR.parent / '同花顺所属概念更新'

# 确保核心目录存在
for d in [DATA_DIR, METADATA_DIR, SAVE_DIR, MARKET_REPORT_DIR, LIMIT_UP_DIR, CONCEPT_DIR, THS_DATA_ROOT]:
    d.mkdir(parents=True, exist_ok=True)

# 核心文件绝对路径
CONCEPT_PATH = METADATA_DIR / '所属概念.csv'
CALENDAR_PATH = METADATA_DIR / '交易日历.csv'
SCHEDULER_STATUS_PATH = METADATA_DIR / 'task_status.txt'
BUSINESS_CONFIG_PATH = METADATA_DIR / 'business_config.json'  # 业务配置文件路径

# 趋势与缓存路径
SENTIMENT_TREND_PATH = MARKET_REPORT_DIR / 'daily_sentiment_trend.csv'
TOP15_CACHE_PATH = MARKET_REPORT_DIR / 'daily_top15_stocks.csv'


# ==================== 2. 业务配置管理 (Business Config) ====================

# 默认配置模板 (当 JSON 文件不存在时使用)
_DEFAULT_CONFIG = {
    "HOT_KEYWORDS": [
        "海南", "海峡两岸", "商业航天", "电子化学", "脑机", "金", "光刻胶"
    ],
    "HOT_CONCEPT_LIST": [
        "海南", "海峡两岸", "商业航天"
    ],
    "BLACKLIST": [
        "融资融券", "深股通", "沪股通", "转融通标的", "证金持股",
        "MSCI概念", "标普道琼斯A股", "沪深300", "预盈预增",
        "地方国资改革", "国企改革"
    ]
}


class ConfigManager:
    """
    业务配置管理器
    支持从 JSON 文件加载配置，如果不存在则使用默认配置
    """
    def __init__(self, config_path: Path = BUSINESS_CONFIG_PATH):
        self.config_path = config_path
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置，如果文件不存在则创建默认配置"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.warning(f"加载配置文件失败: {e}，使用默认配置")
        
        # 创建默认配置文件
        self._save_config(_DEFAULT_CONFIG)
        return _DEFAULT_CONFIG.copy()
    
    def _save_config(self, config: Dict[str, Any]):
        """保存配置到文件"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"保存配置文件失败: {e}")
    
    def get(self, key: str, default=None):
        """获取配置项"""
        return self._config.get(key, default)
    
    def update(self, key: str, value: Any):
        """更新配置项并保存"""
        self._config[key] = value
        self._save_config(self._config)


# 全局配置管理器实例
_config_manager = ConfigManager()

# 便捷访问函数
def get_hot_keywords() -> List[str]:
    """获取热点关键词列表"""
    return _config_manager.get("HOT_KEYWORDS", _DEFAULT_CONFIG["HOT_KEYWORDS"])

def get_hot_concepts() -> List[str]:
    """获取热点概念列表"""
    return _config_manager.get("HOT_CONCEPT_LIST", _DEFAULT_CONFIG["HOT_CONCEPT_LIST"])

def get_blacklist() -> Set[str]:
    """获取黑名单集合"""
    return set(_config_manager.get("BLACKLIST", _DEFAULT_CONFIG["BLACKLIST"]))


# ==================== 3. 列名常量 (Column Constants) ====================

class COL:
    """
    标准列名常量类
    使用方式: COL.CODE, COL.NAME, COL.PRICE 等
    """
    # 基础信息
    CODE = "股票代码"
    NAME = "股票简称"
    
    # 价格
    PRICE = "收盘价"
    YESTERDAY_CLOSE = "昨收盘"
    OPEN = "开盘价"
    HIGH = "最高价"
    LOW = "最低价"
    JJ_PRICE = "竞价价"
    LIMIT_UP_PRICE = "涨停价"
    LIMIT_DOWN_PRICE = "跌停价"
    
    # 涨跌幅
    PCT_CHG = "涨跌幅"
    
    # 成交额 (单位: 元)
    AMOUNT = "成交额"
    JJ_AMOUNT = "竞价成交额"
    
    # 成交量
    VOLUME = "成交量"
    
    # 其他
    TURNOVER = "换手率"
    CONCEPT = "所属概念"
    INDUSTRY = "所属行业"  # ✅ 新增行业常量
    
    # 盘口数据
    BID1_PRICE = "买一价"
    BID1_VOLUME = "买一量"
    ASK1_PRICE = "卖一价"
    ASK1_VOLUME = "卖一量"
    
    # 涨停分析相关
    CONSECUTIVE_LIMIT_UP_DAYS = "连续涨停天数"
    LIMIT_UP_REASON = "涨停原因类别"
    LIMIT_UP_DOWN_STATUS = "涨跌停"
    BOARD_LEVEL = "板次"
    LOCK_AMOUNT = "封单额(亿)"
    HOT_TAGS = "热点关键词"
    
    # 结构标签分析相关
    STRUCTURE_TAG = "结构标签"
    VOLUME_RATIO = "放量倍数"
    
    # Top15 分析相关
    AMOUNT_BILLION = "金额_亿"  # 以亿为单位的金额
    DATA_TYPE = "类型"  # 竞价/收盘
    CONSECUTIVE_DAYS = "出现次数"  # N天内出现次数
    STREAK_DAYS = "连续天数"  # 连续上榜天数
    
    # 题材分析相关
    INCREMENT_BILLION = "增量(亿)"
    CONCEPT_NAME = "题材名称"
    STOCK_COUNT = "家数"
    AVG_CHANGE_PCT = "平均涨跌%"
    TOTAL_AMOUNT_BILLION = "总成交额(亿)"
    RED_RATIO_PCT = "红盘率%"
    INCREMENT_LEADER = "增量先锋"
    LEADER_CODE = "先锋代码"
    
    # 标准列名
    STD_PRICE = "价格"    # 统一价格列名
    STD_AMOUNT = "金额"   # 统一金额列名



# ==================== 4. 列名映射 (Column Mapping) ====================

# 原始列名 -> 标准列名映射
# 使用 MappingProxyType 防止运行时意外修改
COLUMN_MAPPING = MappingProxyType({
    # 基础信息
    "code": COL.CODE,
    "name": COL.NAME,
    "股票名称": COL.NAME,
    
    # 价格相关 - 统一映射到标准价格列
    "now": COL.STD_PRICE,
    "竞价": COL.STD_PRICE,
    "收盘价": COL.STD_PRICE,
    "价格": COL.STD_PRICE,
    "最新价": COL.STD_PRICE,
    "close": COL.YESTERDAY_CLOSE,
    "昨收盘": COL.YESTERDAY_CLOSE,
    "open": COL.OPEN,
    "开盘价": COL.OPEN,
    "high": COL.HIGH,
    "最高价": COL.HIGH,
    "low": COL.LOW,
    "最低价": COL.LOW,
    "limit_up": COL.LIMIT_UP_PRICE,
    "涨停价": COL.LIMIT_UP_PRICE,
    "limit_down": COL.LIMIT_DOWN_PRICE,
    "跌停价": COL.LIMIT_DOWN_PRICE,
    
    # 涨跌幅
    "change": COL.PCT_CHG,
    "涨跌(%)": COL.PCT_CHG,
    "涨跌幅": COL.PCT_CHG,
    "最新涨跌幅": COL.PCT_CHG,
    "pct_chg": COL.PCT_CHG,
    
    # 成交额 - 统一映射到标准金额列
    "amount": COL.STD_AMOUNT,
    "成交额(万)": COL.STD_AMOUNT,
    "金额": COL.STD_AMOUNT,
    "竞价金额": COL.STD_AMOUNT,
    "jj_amount": COL.STD_AMOUNT,
    
    # 其他
    "volume": COL.VOLUME,
    "成交量": COL.VOLUME,
    "turnover": COL.TURNOVER,
    "所属同花顺行业": COL.INDUSTRY,  # ✅ 增加映射
    "所属行业": COL.INDUSTRY,  # ✅ 增加映射（概念数据文件使用）
    
    # 盘口数据
    "bid1": COL.BID1_PRICE,
    "bid1_volume": COL.BID1_VOLUME,
    "ask1": COL.ASK1_PRICE,
    "ask1_volume": COL.ASK1_VOLUME
})


# ==================== 5. 热点关键词与黑名单 (Hot Keywords & Blacklist) ====================

# 热点关键词 (用于标记热门股票)
HOT_KEYWORDS = get_hot_keywords()

# 热点概念列表
HOT_CONCEPT_LIST = get_hot_concepts()

# 概念黑名单 (过滤无效概念)
BLACKLIST = get_blacklist()


# ==================== 6. 日志配置 (Logging) ====================

def setup_logging(
    level: int = logging.INFO,
    log_file: Path = None,
    format_str: str = None
):
    """
    配置日志系统
    
    参数:
        level: 日志级别
        log_file: 日志文件路径 (可选)
        format_str: 日志格式字符串
    """
    if format_str is None:
        format_str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    handlers = [logging.StreamHandler()]
    
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding='utf-8'))
    
    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=handlers,
        force=True
    )


# 默认初始化日志
setup_logging()

# ==================== 定时任务配置 ====================
# 状态记录文件存放在 metadata 目录下
SCHEDULER_STATUS_PATH = METADATA_DIR / 'task_status.txt'

# 任务 ID 与 脚本/标签 的映射（方便统一维护）
SCHEDULED_JOBS = {
    'data_job_morning': {
        'script': 'scripts/daily_market_update.py',
        'label': '竞价抓取',
        'time': {'hour': 9, 'minute': 25}
    },
    'data_job_afternoon': {
        'script': 'scripts/daily_market_update.py',
        'label': '收盘抓取',
        'time': {'hour': 15, 'minute': 5}
    },
    'concept_job': {
        'script': 'scripts/daily_concept_update.py',
        'label': '概念更新',
        'time': {'hour': 17, 'minute': 1}
    }
}