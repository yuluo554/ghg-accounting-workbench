"""三维坐标模型：通则版本 × 年度 × 行业。

坐标的一维化键 = ``<standard>/<year>/<industry>``。
**合法性判据全部来自 data/rules/manifest.json**——代码内不得内联标准短键、年度清单或
行业名（NFR-07 零政策字面量门禁）。
"""

from .errors import CoordinateError


class Coordinate(object):
    """一个规则包坐标。字段值与 manifest 枚举一致。"""

    __slots__ = ("standard", "year", "industry")

    def __init__(self, standard, year, industry):
        if not standard or not industry:
            raise CoordinateError("坐标字段不得为空：%r/%r/%r" % (standard, year, industry))
        try:
            year_int = int(year)
        except (TypeError, ValueError):
            raise CoordinateError("年度必须为整数：%r" % (year,))
        self.standard = str(standard)
        self.year = year_int
        self.industry = str(industry)

    @property
    def key(self):
        return "%s/%d/%s" % (self.standard, self.year, self.industry)

    def as_dict(self):
        return {"standard": self.standard, "year": self.year, "industry": self.industry}

    def __eq__(self, other):
        return isinstance(other, Coordinate) and self.key == other.key

    def __hash__(self):
        return hash(self.key)

    def __repr__(self):
        return "Coordinate(%s)" % self.key

    def __str__(self):
        return self.key


def parse_coordinate(raw, index=None):
    """从 dict 或 ``a/b/c`` 字符串解析坐标。

    传入 index（:class:`ghg.rules.RulesIndex`）时额外校验坐标是否存在于坐标空间。
    """
    if isinstance(raw, Coordinate):
        coord = raw
    elif isinstance(raw, dict):
        missing = [k for k in ("standard", "year", "industry") if k not in raw]
        if missing:
            raise CoordinateError("坐标缺少字段：%s" % "、".join(missing))
        coord = Coordinate(raw["standard"], raw["year"], raw["industry"])
    elif isinstance(raw, str):
        parts = [p.strip() for p in raw.split("/")]
        if len(parts) != 3 or not all(parts):
            raise CoordinateError("坐标字符串须为 <standard>/<year>/<industry>：%r" % raw)
        coord = Coordinate(parts[0], parts[1], parts[2])
    else:
        raise CoordinateError("无法解析坐标：%r" % (type(raw).__name__,))

    if index is not None:
        index.require(coord)
    return coord
