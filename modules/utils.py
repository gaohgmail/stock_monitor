import sys
import pandas as pd
from pathlib import Path
from .config import COLUMN_MAPPING

class Logger:
    """同时输出到控制台和文件的日志器"""
    def __init__(self, filename: str, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        self.terminal = sys.stdout
        self.log = open(path / filename, "w", encoding='utf-8')

    def write(self, message: str):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()
        sys.stdout = self.terminal


def safe_read_csv(file_path: Path) -> pd.DataFrame:
    """安全读取CSV，支持gbk和utf-8-sig编码"""
    if not file_path.exists():
        return pd.DataFrame()
    for encoding in ['gbk', 'utf-8-sig']:
        try:
            return pd.read_csv(file_path, encoding=encoding  , dtype=str)
        except Exception:
            continue
    print(f"⚠️ 无法读取文件（编码失败）：{file_path}")
    return pd.DataFrame()


def standardize_code(code: str) -> str:
    """统一股票代码格式：sh/sz/bj + 6位数字"""
    digits = ''.join(filter(str.isdigit, str(code)))
    if not digits:
        return ''
    digits = digits.zfill(6)
    if digits.startswith('6'):
        return f"sh{digits}"
    if digits[0] in '489':
        return f"bj{digits}"
    return f"sz{digits}"


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """统一清洗：列名映射、代码标准化、去除重复列"""
    if df.empty:
        return df

    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns=COLUMN_MAPPING)

    # 去除重复列
    df = df.loc[:, ~df.columns.duplicated()]

    # 标准化股票代码
    if '股票代码' in df.columns:
        df['股票代码'] = df['股票代码'].apply(standardize_code)

    return df

def print_md_table(df: pd.DataFrame, title: str, subtitle: str = ""):
    """打印Markdown格式的表格"""
    if df.empty:
        return
    print(f"\n### {title}")
    if subtitle:
        print(f"*{subtitle}*")
    print(df.to_markdown(index=False))
    print("\n")
