"""Bölüm numaralandırması için açık alanlardan oluşan tablo."""
from PySide6.QtWidgets import QTableWidget, QSpinBox, QComboBox, QCheckBox, QHeaderView
from ui import qt_compat as ctk
from ui.theme import FORMAT_LABELS
from ui.i18n import tr


class SectionEditor(QTableWidget, ctk.QtWidgetMixin):
    def __init__(self, master, on_change):
        super().__init__(0, 5, master._content_host())
        self._init_mixin(master)
        self._changed = on_change
        self.refresh_language()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setStretchLastSection(True)
        self.setMinimumHeight(150)

    def add_section(self, data=None, notify=True):
        data = data or {}
        row = self.rowCount()
        self.insertRow(row)
        for col, key in ((0, "start_page"), (1, "start_num")):
            widget = QSpinBox(self)
            widget.setRange(1 if col == 0 else 0, 100000)
            widget.setValue(int(data.get(key, 1)))
            widget.valueChanged.connect(lambda _v: self._changed())
            self.setCellWidget(row, col, widget)
        menu = QComboBox(self)
        for label, code in FORMAT_LABELS.items():
            menu.addItem(tr(label), code)
        menu.setCurrentIndex(max(0, menu.findData(data.get("format_style", "number"))))
        menu.currentIndexChanged.connect(lambda _v: self._changed())
        self.setCellWidget(row, 2, menu)
        for col, key in ((3, "hide_first"), (4, "blank_before")):
            box = QCheckBox(self)
            box.setChecked(bool(data.get(key, False)))
            box.toggled.connect(lambda _v: self._changed())
            self.setCellWidget(row, col, box)
        if notify:
            self._changed()

    def remove_selected(self):
        rows = sorted({index.row() for index in self.selectedIndexes()}, reverse=True)
        if not rows and self.rowCount():
            rows = [self.rowCount() - 1]
        for row in rows:
            self.removeRow(row)
        self._changed()

    def sections(self):
        return [dict(start_page=self.cellWidget(r, 0).value(), start_num=self.cellWidget(r, 1).value(),
                     format_style=self.cellWidget(r, 2).currentData(),
                     hide_first=self.cellWidget(r, 3).isChecked(), blank_before=self.cellWidget(r, 4).isChecked())
                for r in range(self.rowCount())]

    def set_sections(self, values):
        self.setRowCount(0)
        for value in values:
            self.add_section(value, notify=False)

    def refresh_language(self):
        self.setHorizontalHeaderLabels([tr(value) for value in
                                        ("Başlangıç sayfası", "İlk numara", "Biçim", "İlkinde gizle", "Sağ sayfada başla")])
        for row in range(self.rowCount()):
            menu = self.cellWidget(row, 2)
            if menu is not None:
                previous = menu.blockSignals(True)
                for index, label in enumerate(FORMAT_LABELS):
                    menu.setItemText(index, tr(label))
                menu.blockSignals(previous)
