from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QSpinBox, QDoubleSpinBox
from pathlib import Path
import yaml


class AnalysisSettings(QWidget):
    def __init__(self):
        super().__init__()
        from app_paths import resource_path
        configuration = yaml.safe_load(resource_path('config/config.yaml').read_text(encoding='utf-8')) or {}
        layout = QHBoxLayout(self)
        self.iterations = QComboBox()
        for value in (10000, 50000, 100000, 500000, 1000000):
            self.iterations.addItem(f'{value:,}', value)
        index = self.iterations.findData(configuration.get('simulations', 100000))
        self.iterations.setCurrentIndex(index if index >= 0 else 2)
        self.seed = QSpinBox()
        self.seed.setRange(0, 2147483647)
        self.seed.setValue(int(configuration.get('seed', 42)))
        self.fold = QDoubleSpinBox()
        self.fold.setRange(0, 1)
        self.fold.setSingleStep(0.05)
        for text, widget in [('模擬次數', self.iterations), ('亂數種子', self.seed), ('情境棄牌率', self.fold)]:
            layout.addWidget(QLabel(text))
            layout.addWidget(widget)
