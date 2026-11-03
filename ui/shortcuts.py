"""Klavye kısayolları ve ana eylem yönlendirmesi."""

from __future__ import annotations

from PySide6.QtWidgets import QLineEdit, QTextEdit

from ui import qt_compat as ctk


class ShortcutsMixin:
    """Kısayol bağları; Birleştirme sekmesinde liste kısayolları, diğerlerinde ana eylem."""

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-o>", lambda e: self._choose_file())
        self.bind("<Control-O>", lambda e: self._choose_file())
        # Ctrl+S "işle" anlamına geliyordu; asıl eylem Ctrl+Enter oldu.
        self.bind("<Control-Return>", lambda e: self._invoke_main_action())
        self.bind("<Return>", self._on_enter_key)
        self.bind("<Escape>", lambda e: self._on_escape())
        self.bind("<Delete>", self._on_merge_delete)
        self.bind("<Alt-Up>", lambda e: self._on_merge_move(-1))
        self.bind("<Alt-Down>", lambda e: self._on_merge_move(1))

    def _list_shortcuts_active(self) -> bool:
        """Liste kısayolları yalnızca birleştirme sekmesinde ve metin alanı dışında çalışır."""
        if "Birleştirme" not in self.tabview.get():
            return False
        focus = self.focus_get()
        return not isinstance(focus, (QLineEdit, QTextEdit, ctk.CTkEntry, ctk.CTkTextbox))

    def _on_enter_key(self, _event=None):
        focus = self.focus_get()
        if isinstance(focus, (QLineEdit, QTextEdit, ctk.CTkEntry, ctk.CTkTextbox)):
            return
        self._invoke_main_action()

    def _on_escape(self) -> None:
        if self._busy:
            self._cancel_work()

    def _invoke_main_action(self) -> None:
        if self._busy:
            return
        if "Birleştirme" in self.tabview.get():
            self._start_merging()
        else:
            self._start_processing()

    def _on_merge_delete(self, _event=None):
        if not self._list_shortcuts_active() or self._busy:
            return None
        self._tabs["Birleştirme"].remove_selected()
        return "break"

    def _on_merge_move(self, delta: int):
        if not self._list_shortcuts_active() or self._busy:
            return None
        tab = self._tabs["Birleştirme"]
        if delta < 0:
            tab.move_up()
        else:
            tab.move_down()
        return "break"
