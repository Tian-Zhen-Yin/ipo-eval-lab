"""引擎侧错误（AR4：坏输入起不了 run）。"""


class EngineError(Exception):
    """run 装配期失败：公司不存在 / 坐标非法 / 规则库 lint 红等。"""
