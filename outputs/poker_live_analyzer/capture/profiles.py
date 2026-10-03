from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class Region:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self):
        values = (self.x, self.y, self.width, self.height)
        if not all(math.isfinite(v) for v in values) or min(values) < 0:
            raise ValueError('區域座標必須是非負有限數值')
        if self.width <= 0 or self.height <= 0 or self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError('區域必須位於畫面內並具有正面積')


@dataclass
class TableProfile:
    regions: dict[str, Region]

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({k: asdict(v) for k, v in self.regions.items()}, ensure_ascii=False, indent=2), encoding='utf-8')

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return cls({name: Region(**region) for name, region in data.items()})
