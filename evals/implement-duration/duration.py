"""時間長度的解析與格式化。規格見 SPEC.md。"""


def parse_duration(text: str) -> int:
    """把 "1h30m"、"90s"、"2d 4h" 這類字串轉成總秒數。"""
    raise NotImplementedError


def format_duration(seconds: int) -> str:
    """把總秒數轉成最精簡的 "1d2h3m4s" 形式。"""
    raise NotImplementedError
