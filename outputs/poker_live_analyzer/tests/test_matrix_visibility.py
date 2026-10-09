import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from ui.threat_matrix import ThreatMatrix


@pytest.mark.parametrize('size',[(448,350),(640,450),(1000,700)])
def test_all_matrix_cells_are_visible_without_scrollbars(size):
    app=QApplication.instance() or QApplication([])
    matrix=ThreatMatrix()
    matrix.resize(*size)
    matrix.show()
    for _ in range(3): app.processEvents()
    table=matrix.table
    assert table.horizontalScrollBarPolicy()==Qt.ScrollBarAlwaysOff
    assert table.verticalScrollBarPolicy()==Qt.ScrollBarAlwaysOff
    assert table.horizontalScrollBar().maximum()==0
    assert table.verticalScrollBar().maximum()==0
    for row in range(13):
        for column in range(13):
            assert table.viewport().rect().contains(table.visualItemRect(table.item(row,column)))
    matrix.close()
