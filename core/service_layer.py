# -*- coding: utf-8 -*-
"""
市场数据服务层 (Market Data Service Layer)

功能：
1. 提供统一的市场数据获取接口
2. 实现多级缓存策略（内存 -> 文件 -> 实时计算）
3. 自动持久化计算结果
4. 提供批量并发数据处理工具

使用示例:
    from service_layer import market_service, MarketStage

    # 1. 获取市场情绪
    df = market_service.get_market_sentiment([datetime(2026, 2, 6)])

    # 2. 获取涨停数据
    df = market_service.get_limit_up_data(datetime(2026, 2, 6), stage=MarketStage.CLOSE)

    # 3. 批量获取（自动并发）
    df_batch = get_limit_up_batch(dates, stage=MarketStage.AUCTION, max_workers=4)
"""

import os
from typing import Optional, Dict, Any, Tuple, List, Callable, Union
from datetime import datetime, time, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
import pandas as pd

# ----------------------------------------------------------------------------
# 业务模块导入
# ----------------------------------------------------------------------------
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from modules.analyzer_market_1 import get_sentiment_trend_report
from modules.analyzer_limit_tags import analyze_limit_up_tags
from modules.df_concepts import get_concepts_data
from modules.top15_JISUAN import calculate_and_save_top15 as calc_and_save_top15
from tools.config import (
    MARKET_REPORT_DIR,
    LIMIT_UP_DIR,
    CONCEPT_DIR,
    DATA_DIR,
    TOP15_CACHE_PATH,
    COL
)
from tools.data_loader import get_trade_dates


# ============================================================================
# 1. 基础类型与枚举定义
# ============================================================================

class DataStatus(str, Enum):
    """数据状态响应码"""
    OK = "ok"
    NOT_CLOSE_TIME = "not_close_time"
    RAW_DATA_MISSING = "raw_missing"
    EMPTY_RESULT = "empty"
    ERROR = "error"


class MarketStage(str, Enum):
    """市场阶段枚举"""
    AUCTION = "竞价"
    CLOSE = "收盘"


@dataclass
class DataResult:
    """标准数据返回包装类"""
    data: Any  # 通常是 pd.DataFrame 或 Tuple[pd.DataFrame]
    status: DataStatus
    message: str

    def is_ok(self) -> bool:
        return self.status == DataStatus.OK

    def is_empty(self) -> bool:
        return self.status == DataStatus.EMPTY_RESULT


# ============================================================================
# 2. 基础设施层 (缓存与存储)
# ============================================================================

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

    def delete(self, key: str) -> None:
        if self.enabled and key in self._cache:
            del self._cache[key]

    def clear(self) -> None:
        self._cache.clear()

    def info(self) -> Dict[str, Any]:
        return {
            'enabled': self.enabled,
            'count': len(self._cache),
            'keys': list(self._cache.keys())
        }


class FileStorage:
    """文件持久化管理器"""

    def __init__(self, auto_save: bool = True):
        self.auto_save = auto_save

    def load(self, file_path: Path) -> Optional[pd.DataFrame]:
        """从CSV加载DataFrame，处理空文件或格式错误"""
        if not file_path.exists():
            return None

        try:
            # 快速检查文件大小
            if file_path.stat().st_size == 0:
                print(f"📂 文件为空: {file_path.name}")
                return None

            df = pd.read_csv(file_path, encoding='utf-8-sig')
            if df.empty:
                return None
            
            # 简化日志，只在非批量模式下开启调试可能更好，这里保留原意
            # print(f"📂 从文件加载: {file_path.name} ({len(df)}条)")
            return df

        except (pd.errors.EmptyDataError, Exception) as e:
            print(f"⚠️ 加载文件异常 {file_path.name}: {e}")
            return None

    def save(self, df: pd.DataFrame, file_path: Path) -> Optional[str]:
        """保存DataFrame到CSV"""
        if not self.auto_save or df is None:
            return None

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(file_path, index=False, encoding='utf-8-sig', float_format='%.2f')
            print(f"💾 已保存: {file_path.name}")
            return str(file_path)
        except Exception as e:
            print(f"❌ 保存失败 {file_path}: {e}")
            return None


class DataValidator:
    """业务规则验证器"""

    @staticmethod
    def check_close_time(target_date: datetime) -> bool:
        """判断是否满足查看收盘数据的时间条件 (T日15:00后)"""
        now = datetime.now()
        target_date_obj = target_date.date() if isinstance(target_date, datetime) else target_date
        
        if target_date_obj < now.date():
            return True
        if target_date_obj == now.date():
            return now.time() >= time(15, 0)
        return False

    @staticmethod
    def check_raw_data_exists(target_date: datetime, data_type: str) -> bool:
        """检查基础行情文件是否存在"""
        date_str = target_date.strftime('%Y-%m-%d')
        file_path = DATA_DIR / f"{date_str}_{data_type}.csv"
        return file_path.exists()


# ============================================================================
# 3. 核心服务层
# ============================================================================

class MarketService:
    """
    市场数据核心服务
    
    调用链路: Memory Cache -> File Cache -> Raw Data Check -> Compute -> Save -> Update Cache
    """

    def __init__(self, auto_save: bool = True, use_cache: bool = True):
        self.cache = CacheManager(enabled=use_cache)
        self.storage = FileStorage(auto_save=auto_save)
        self.validator = DataValidator()
        self._init_dirs()

    def _init_dirs(self):
        for d in [MARKET_REPORT_DIR, LIMIT_UP_DIR, CONCEPT_DIR]:
            d.mkdir(parents=True, exist_ok=True)

    def _get_data_flow(
        self,
        cache_key: str,
        file_path: Path,
        compute_func: Callable[[], Any],
        check_raw_func: Callable[[], bool],
        status_msg_func: Callable[[], Tuple[DataStatus, str]]
    ) -> DataResult:
        """通用的数据获取流程模版方法"""
        
        # 1. 内存缓存
        cached = self.cache.get(cache_key)
        if cached is not None:
            print(f"⚡ 内存命中: {cache_key}")
            return DataResult(cached, DataStatus.OK, '内存缓存')

        # 2. 文件缓存
        df = self.storage.load(file_path)
        if df is not None:
            status = DataStatus.OK if not df.empty else DataStatus.EMPTY_RESULT
            # 对于多返回值的情况(如题材)，需要特殊处理，这里主要处理单个DF的情况
            self.cache.set(cache_key, df)
            return DataResult(df, status, '文件缓存')

        # 3. 检查原始数据依赖
        if not check_raw_func():
            status, msg = status_msg_func()
            return DataResult(pd.DataFrame(), status, msg)

        # 4. 实时计算
        try:
            result = compute_func()
        except Exception as e:
            print(f"❌ 计算异常: {e}")
            return DataResult(pd.DataFrame(), DataStatus.ERROR, str(e))

        # 5. 处理结果与持久化
        # 处理题材数据返回 (stats, details) 的特殊情况
        if isinstance(result, tuple) and len(result) == 2:
            df_stats, df_details = result
            # 注意：此处假设调用方会处理具体的保存逻辑，或者 compute_func 内部不保存
            # 这是一个通用模版，如果返回值结构差异大，建议拆分。
            # 为了保持通用性，我们在具体方法里处理保存，这里只做流程控制。
            pass
        else:
            # 假设是单个 DataFrame
            self.storage.save(result, file_path)
        
        self.cache.set(cache_key, result)
        
        # 构造返回
        is_empty = result.empty if isinstance(result, pd.DataFrame) else (result[0].empty if isinstance(result, tuple) else True)
        status = DataStatus.EMPTY_RESULT if is_empty else DataStatus.OK
        return DataResult(result, status, '计算完成')

    # ------------------------------------------------------------------------
    # 公共接口 API
    # ------------------------------------------------------------------------

    def get_market_sentiment ( self , date_list : List [ datetime ]) -> pd . DataFrame :
            """获取市场情绪数据 (增加容错校验)"""
            if not date_list : return pd . DataFrame ()
            
            cache_key = "sentiment_full_data"
            full_data = self . cache . get ( cache_key )
            
            if full_data is None :
                try :
                    full_data = get_sentiment_trend_report ( date_list )
                except Exception as e :
                    print ( f"⚠️ 加载情绪数据失败: { e } " )
                    full_data = pd . DataFrame ()
                self . cache . set ( cache_key , full_data )
    
            # --- 增加以下容错逻辑 ---
            if full_data is None or full_data.empty:
                print("⚠️ 情绪数据为空，无法进行筛选")
                return pd.DataFrame()
    
            if '日期' not in full_data.columns:
                print(f"❌ 关键错误：数据中缺少 '日期' 列。当前列名: {full_data.columns.tolist()}")
                # 尝试修复：如果第一列没名字，可能就是日期
                if full_data.iloc[:, 0].dtype == object: 
                    full_data.rename(columns={full_data.columns[0]: '日期'}, inplace=True)
                else:
                    return pd.DataFrame()
        # -----------------------

            date_strs = [ d . strftime ( '%Y-%m-%d' ) for d in date_list ]
            result = full_data [ full_data [ '日期' ]. isin ( date_strs )]. copy ()
            return result

    def get_limit_up_data(self, date: datetime, stage: Union[str, MarketStage] = MarketStage.CLOSE) -> DataResult:
        """获取涨停数据"""
        stage_str = stage.value if isinstance(stage, MarketStage) else stage
        
        cache_key = self.cache.get_key("limit_up", date, stage=stage_str)
        file_path = LIMIT_UP_DIR / f"limit_up_{stage_str}_{date.strftime('%Y%m%d')}.csv"
        raw_type = '收盘行情' if stage_str == MarketStage.CLOSE else '竞价行情'

        def check_raw():
            return self.validator.check_raw_data_exists(date, raw_type)

        def get_status_msg():
            if stage_str == MarketStage.CLOSE and not self.validator.check_close_time(date):
                return DataStatus.NOT_CLOSE_TIME, f'{date.date()} 收盘数据未生成'
            return DataStatus.RAW_DATA_MISSING, f'{date.date()} {stage_str} 原始数据缺失'

        def compute():
            print(f"🔧 计算涨停: {date.date()} {stage_str}")
            return analyze_limit_up_tags(date, stage=stage_str)

        return self._get_data_flow(cache_key, file_path, compute, check_raw, get_status_msg)

    def get_concept_data(self, date: datetime, data_type: Union[str, MarketStage] = MarketStage.AUCTION) -> Tuple[DataResult, DataResult]:
        """获取题材数据 (返回 Stats, Details)"""
        type_str = data_type.value if isinstance(data_type, MarketStage) else data_type
        
        cache_key = self.cache.get_key("concept", date, data_type=type_str)
        stats_path = CONCEPT_DIR / f"concept_stats_{type_str}_{date.strftime('%Y%m%d')}.csv"
        details_path = CONCEPT_DIR / f"stock_details_{type_str}_{date.strftime('%Y%m%d')}.csv"
        raw_type = '竞价行情' if type_str == MarketStage.AUCTION else '收盘行情'

        # 1. 内存缓存
        cached = self.cache.get(cache_key)
        if cached:
            print(f"⚡ 内存命中: {cache_key}")
            return (DataResult(cached[0], DataStatus.OK, '内存缓存'), 
                    DataResult(cached[1], DataStatus.OK, '内存缓存'))

        # 2. 文件缓存 (需要两个文件都存在)
        df_stats = self.storage.load(stats_path)
        df_details = self.storage.load(details_path)
        
        if df_stats is not None and df_details is not None:
            self.cache.set(cache_key, (df_stats, df_details))
            return (DataResult(df_stats, DataStatus.OK, '文件缓存'),
                    DataResult(df_details, DataStatus.OK, '文件缓存'))

        # 3. 原始数据检查
        if not self.validator.check_raw_data_exists(date, raw_type):
            msg = f"{date.date()} {type_str} 原始数据缺失"
            status = DataStatus.RAW_DATA_MISSING
            if type_str == MarketStage.CLOSE and not self.validator.check_close_time(date):
                msg = f"{date.date()} 收盘数据未生成"
                status = DataStatus.NOT_CLOSE_TIME
            return (DataResult(pd.DataFrame(), status, msg), 
                    DataResult(pd.DataFrame(), status, msg))

        # 4. 计算
        print(f"🔧 计算题材: {date.date()} {type_str}")
        try:
            df_stats, df_details = get_concepts_data(date, data_type=type_str)
        except Exception as e:
            err = DataResult(pd.DataFrame(), DataStatus.ERROR, str(e))
            return err, err

        # 5. 保存
        self.storage.save(df_stats, stats_path)
        self.storage.save(df_details, details_path)
        
        # 6. 更新缓存
        self.cache.set(cache_key, (df_stats, df_details))
        
        status = DataStatus.EMPTY_RESULT if df_stats.empty else DataStatus.OK
        return (DataResult(df_stats, status, '计算完成'),
                DataResult(df_details, status, '计算完成'))

    def get_top15_data(self, target_date: datetime, trend_days: int = 30) -> pd.DataFrame:
        """获取 Top15 数据 (一次性读取整个文件到内存，然后查询)"""
        date_str = target_date.strftime('%Y-%m-%d')
        
        # 1. 检查是否已加载整个Top15文件到内存
        cache_key = "top15_full_data"
        full_data = self.cache.get(cache_key)
        
        if full_data is None:
            # 首次访问，触发增量计算
            print(f"📊 首次加载Top15数据...")
            try:
                full_data = calc_and_save_top15()
                # 去重：根据日期、类型、股票代码
                if not full_data.empty and '日期' in full_data.columns:
                    full_data = full_data.drop_duplicates(subset=['日期', '类型', '股票代码'], keep='last')
                print(f"✅ Top15数据已加载到内存，共 {len(full_data)} 条记录")
            except Exception as e:
                print(f"⚠️ 加载Top15数据失败: {e}")
                full_data = pd.DataFrame()
            
            self.cache.set(cache_key, full_data)
        
        # 2. 从内存中筛选需要的日期数据
        # 将日期转换为字符串格式进行筛选
        if '日期' in full_data.columns:
            full_data['日期'] = full_data['日期'].astype(str)
        
        result = full_data[full_data['日期'] == date_str].copy()
        
        if not result.empty:
            print(f"⚡ 内存查询 Top15: {date_str} 共 {len(result)} 条记录")
        else:
            print(f"⚠️ 内存查询 Top15: {date_str} 未找到数据")
            
        return result

    def search_concept_history(self, concept_name: str, days: int = 30) -> pd.DataFrame:
        """搜索指定题材的历史数据（统一走 Service 层，带缓存）
        
        Args:
            concept_name: 题材名称
            days: 获取最近多少个交易日的数据
            
        Returns:
            包含该题材历史数据的 DataFrame
        """
        try:
            # 1. 检查内存缓存
            cache_key = self.cache.get_key("concept_history", datetime.now(), concept=concept_name, days=days)
            cached = self.cache.get(cache_key)
            if cached is not None:
                print(f"⚡ 内存命中: {cache_key}")
                return cached
            
            # 2. 获取最近 N 个交易日（自动处理周末/节假日）
            date_list = get_trade_dates(days)
            
            # 3. 批量获取这些天的题材数据（自动走缓存流程，缺失的自动计算）
            df_stats_all, _ = get_concept_batch(date_list, MarketStage.CLOSE, max_workers=4)
            
            if df_stats_all.empty or '题材名称' not in df_stats_all.columns:
                self.cache.set(cache_key, pd.DataFrame())
                return pd.DataFrame()
            
            # 4. 筛选指定题材
            result = df_stats_all[df_stats_all['题材名称'] == concept_name].copy()
            
            if result.empty:
                self.cache.set(cache_key, pd.DataFrame())
                return pd.DataFrame()
            
            # 5. 格式化小数列（保留两位小数），和 CSV 保存格式一致
            float_columns = ['增量(亿)', '平均涨跌%', '金额(亿)']
            for col in float_columns:
                if col in result.columns:
                    result[col] = pd.to_numeric(result[col], errors='coerce').round(2)
            
            # 6. 按日期倒序排列
            if '日期' in result.columns:
                try:
                    result['日期'] = pd.to_datetime(result['日期'])
                    result = result.sort_values('日期', ascending=False)
                except Exception:
                    pass
            
            # 7. 存入内存缓存
            self.cache.set(cache_key, result)
            
            print(f"📊 题材历史查询: {concept_name}，找到 {len(result)} 天数据")
            return result
            
        except Exception as e:
            print(f"❌ 搜索题材历史失败: {e}")
            return pd.DataFrame()
    
    def clear_memory_cache(self):
        self.cache.clear()
        print("🧹 内存缓存已清空")


# 全局单例
market_service = MarketService()


# ============================================================================
# 4. 批量处理工具函数 (Module Level Utilities)
# ============================================================================

def _batch_process(
    dates: List[datetime],
    file_pattern_func: Callable[[datetime], Path],
    compute_func: Callable[[datetime], Any],
    max_workers: int = None,
    desc: str = "数据"
) -> List[Any]:
    """通用批量处理核心逻辑：加载现有 -> 计算缺失 -> 合并结果"""
    
    results = []
    missing_dates = []

    # 1. 尝试加载现有文件
    for date in dates:
        fpath = file_pattern_func(date)
        if fpath.exists():
            try:
                # 简单读取，不进行复杂校验，由后续合并处理
                # 这里假设只要文件存在即有效，具体内容解析交给业务层
                results.append((date, 'file', fpath))
            except Exception:
                missing_dates.append(date)
        else:
            missing_dates.append(date)

    # 2. 计算缺失数据
    if missing_dates:
        print(f"🔧 {desc}: 需计算 {len(missing_dates)}/{len(dates)} 天 (并发: {max_workers or 'Serial'})")
        
        def safe_compute(d):
            try:
                return (d, 'computed', compute_func(d))
            except Exception as e:
                print(f"❌ {desc}计算失败 {d.date()}: {e}")
                return (d, 'error', None)

        if max_workers and max_workers > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(safe_compute, d): d for d in missing_dates}
                for future in as_completed(futures):
                    results.append(future.result())
        else:
            for d in missing_dates:
                results.append(safe_compute(d))

    # 3. 排序保持日期顺序
    results.sort(key=lambda x: x[0])
    return results


def get_limit_up_batch(
    dates: List[datetime], 
    stage: Union[str, MarketStage] = MarketStage.CLOSE,
    max_workers: int = 4
) -> pd.DataFrame:
    """
    批量获取涨停数据 (自动合并文件缓存与实时计算)
    
    Args:
        dates: 日期列表
        stage: '竞价' 或 '收盘'
        max_workers: 并发线程数，None或1为串行
    """
    stage_str = stage.value if isinstance(stage, MarketStage) else stage
    
    def get_path(d):
        return LIMIT_UP_DIR / f"limit_up_{stage_str}_{d.strftime('%Y%m%d')}.csv"
    
    def do_compute(d):
        res = market_service.get_limit_up_data(d, stage=stage_str)
        return res.data if res.is_ok() else None

    raw_results = _batch_process(dates, get_path, do_compute, max_workers, f"涨停[{stage_str}]")
    
    dfs = []
    for date, source, content in raw_results:
        df = None
        if source == 'file':
            df = market_service.storage.load(content) # 复用 storage 的加载逻辑
        elif source == 'computed':
            df = content
            
        if df is not None and not df.empty:
            df['日期'] = date.strftime('%Y-%m-%d')
            # 确保代码列为字符串
            if '代码' in df.columns:
                df['代码'] = df['代码'].astype(str)
            dfs.append(df)
            
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def get_concept_batch(
    dates: List[datetime], 
    data_type: Union[str, MarketStage] = MarketStage.AUCTION,
    max_workers: int = 4
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    批量获取题材数据
    
    Returns:
        (stats_df_all, details_df_all)
    """
    type_str = data_type.value if isinstance(data_type, MarketStage) else data_type

    def get_path(d):
        # 只要 stats 文件存在就认为缓存有效
        return CONCEPT_DIR / f"concept_stats_{type_str}_{d.strftime('%Y%m%d')}.csv"

    def do_compute(d):
        res_stats, res_details = market_service.get_concept_data(d, data_type=type_str)
        return (res_stats.data, res_details.data) if res_stats.is_ok() else None

    raw_results = _batch_process(dates, get_path, do_compute, max_workers, f"题材[{type_str}]")

    all_stats, all_details = [], []
    
    for date, source, content in raw_results:
        stats, details = None, None
        
        if source == 'file':
            # 重新加载两个文件
            stats = market_service.storage.load(content)
            details_path = CONCEPT_DIR / f"stock_details_{type_str}_{date.strftime('%Y%m%d')}.csv"
            details = market_service.storage.load(details_path)
        elif source == 'computed' and content:
            stats, details = content

        date_str = date.strftime('%Y-%m-%d')
        if stats is not None and not stats.empty:
            stats['日期'] = date_str
            all_stats.append(stats)
        if details is not None and not details.empty:
            details['日期'] = date_str
            all_details.append(details)

    return (
        pd.concat(all_stats, ignore_index=True) if all_stats else pd.DataFrame(),
        pd.concat(all_details, ignore_index=True) if all_details else pd.DataFrame()
    )


def warmup_cache(dates: List[datetime], verbose: bool = True) -> Dict[str, Any]:
    """缓存预热工具"""
    stats = {'success': 0, 'failed': 0, 'skipped': 0}
    
    print(f"🔥 开始预热 {len(dates)} 天的数据...")
    
    # 使用串行调用即可，因为底层 get_limit_up_data 等方法已经包含了完整的流程
    # 如果需要并发预热，可以直接调用 get_limit_up_batch(dates, max_workers=4)
    
    # 这里演示并发预热
    try:
        # 1. 涨停数据
        get_limit_up_batch(dates, MarketStage.CLOSE, max_workers=4)
        get_limit_up_batch(dates, MarketStage.AUCTION, max_workers=4)
        
        # 2. 题材数据
        get_concept_batch(dates, MarketStage.AUCTION, max_workers=4)
        get_concept_batch(dates, MarketStage.CLOSE, max_workers=4)
        
        stats['success'] = len(dates) # 简化统计
    except Exception as e:
        print(f"❌ 预热过程出错: {e}")
        stats['failed'] += 1
        

    return stats

