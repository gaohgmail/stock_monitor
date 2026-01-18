from pathlib import Path
import os

# ==================== 路径配置 ====================
# 使用相对路径，确保在 GitHub Actions 和 Streamlit Cloud 都能运行
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data' / 'raw'
METADATA_DIR = BASE_DIR / 'metadata'
CONCEPT_PATH = METADATA_DIR / '所属概念.csv'
CALENDAR_PATH = METADATA_DIR / '交易日历.csv'
SAVE_DIR = BASE_DIR / 'analysis_results'

# 确保必要的目录存在
for d in [DATA_DIR, SAVE_DIR, METADATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ==================== 业务配置 ====================
HOT_KEYWORDS = ['海南', '海峡两岸', '商业航天', '电子化学', '脑机', '光刻胶']
HOT_CONCEPT_LIST = ['海南', '海峡两岸', '商业航天']

BLACKLIST = {
    '融资融券', '深股通', '沪股通', '转融通标的', '证金持股',
    'MSCI概念', '标普道琼斯A股', '沪深300', '预盈预增',
    '地方国资改革', '国企改革'
}

COLUMN_MAPPING = {
    "code": "股票代码", "name": "股票简称","涨跌(%)": "涨跌幅", "成交额(万)": "成交额",
    "now": "收盘价","close": "昨收盘","open": "竞价价","high": "最高价","low": "最低价",
    "bid1": "买一价",
    "bid1_volume": "买一量",
    "ask1": "卖一价",
    "ask1_volume": "卖一量"
}
