"""Обработка физических правых Ctrl/Shift через Windows low-level keyboard hook.

Модуль не обращается к Tkinter напрямую: системный callback только кладёт
события в очередь, а переданные callbacks вызываются из главного потока GUI.
"""
from __future__ import annotations

import ctypes
import queue
from ctypes import wintypes
from typing import Callable


WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
VK_RSHIFT, VK_RCONTROL = 0xA1, 0xA3


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KeyboardListener:
    """Отслеживает правые Ctrl/Shift и делегирует управление записью."""

    def __init__(
        self,
        start_recording: Callable[[str], None],
        promote_to_dictation: Callable[[], None],
        stop_recording: Callable[[], None],
    ) -> None:
        self._start_recording = start_recording
        self._promote_to_dictation = promote_to_dictation
        self._stop_recording = stop_recording
        self._events: queue.SimpleQueue[tuple[int, int]] = queue.SimpleQueue()
        self._pressed: set[int] = set()
        self._hook = None
        self._hook_proc = None
        self._user32 = None

    def _native_keyboard_event(self, n_code, w_param, l_param):
        # Системный callback только передаёт событие в очередь.
        if n_code >= 0 and w_param in (WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP):
            try:
                vk = ctypes.cast(
                    l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)
                ).contents.vkCode
                if vk in (VK_RCONTROL, VK_RSHIFT):
                    self._events.put((vk, w_param))
            except Exception:
                pass
        return self._user32.CallNextHookEx(
            self._hook, n_code, w_param, l_param
        )

    def process_events(self) -> None:
        """Обрабатывает накопленные события в главном потоке приложения."""
        while True:
            try:
                vk, event = self._events.get_nowait()
            except queue.Empty:
                break

            if event in (WM_KEYDOWN, WM_SYSKEYDOWN):
                if vk in self._pressed:
                    continue
                self._pressed.add(vk)

                if vk == VK_RCONTROL:
                    mode = "text" if VK_RSHIFT in self._pressed else "command"
                    self._start_recording(mode)
                elif VK_RCONTROL in self._pressed:
                    self._promote_to_dictation()
            else:
                self._pressed.discard(vk)
                if vk == VK_RSHIFT:
                    # Правая Shift завершает только режим диктовки.
                    # Проверка режима остаётся внутри callback приложения.
                    self._stop_dictation_if_active()
                elif vk == VK_RCONTROL:
                    self._stop_recording()

    def _stop_dictation_if_active(self) -> None:
        """Оставлено отдельным callback, чтобы не переносить состояние записи сюда."""
        if self._is_dictation_active is not None and self._is_dictation_active():
            self._stop_recording()

    def set_dictation_state_callback(
        self, is_dictation_active: Callable[[], bool]
    ) -> None:
        self._is_dictation_active = is_dictation_active

    _is_dictation_active: Callable[[], bool] | None = None

    def install(self) -> None:
        """Устанавливает Windows hook. Вызывается после инициализации GUI."""
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.SetWindowsHookExW.argtypes = (
            ctypes.c_int, ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
            ), wintypes.HINSTANCE, wintypes.DWORD
        )
        self._user32.SetWindowsHookExW.restype = wintypes.HHOOK
        self._user32.CallNextHookEx.argtypes = (
            wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )
        self._user32.CallNextHookEx.restype = ctypes.c_ssize_t
        self._user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
        self._user32.UnhookWindowsHookEx.restype = wintypes.BOOL

        hook_proc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )
        self._hook_proc = hook_proc_type(self._native_keyboard_event)
        self._hook = self._user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._hook_proc, None, 0
        )
        if not self._hook:
            raise ctypes.WinError(ctypes.get_last_error())

    def remove(self) -> None:
        """Снимает hook и очищает физическое состояние клавиш."""
        if self._hook and self._user32 is not None:
            self._user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        self._hook_proc = None
        self._pressed.clear()
