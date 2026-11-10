import unittest
from unittest.mock import Mock

from assistant_window import AssistantWindow


class FakeRoot:
    def __init__(self):
        self.calls = []
        self.window_state = "normal"

    def overrideredirect(self, value):
        self.calls.append(("overrideredirect", value))

    def iconify(self):
        self.calls.append(("iconify", None))
        self.window_state = "iconic"

    def state(self):
        return self.window_state

    def after_idle(self, callback):
        self.calls.append(("after_idle", None))
        callback()


class AssistantWindowMinimizeTests(unittest.TestCase):
    def setUp(self):
        self.window = object.__new__(AssistantWindow)
        self.window.root = FakeRoot()
        self.window._apply_windows_taskbar_style = Mock()

    def test_minimize_disables_override_redirect_before_iconify(self):
        self.window._minimize_window()

        self.assertEqual(
            self.window.root.calls,
            [("overrideredirect", False), ("iconify", None)],
        )

    def test_map_restores_frameless_style_after_window_is_restored(self):
        self.window._on_window_map()

        self.assertEqual(
            self.window.root.calls,
            [
                ("after_idle", None),
                ("overrideredirect", True),
            ],
        )
        self.window._apply_windows_taskbar_style.assert_called_once_with()

    def test_map_does_not_restore_style_while_window_is_minimized(self):
        self.window.root.window_state = "iconic"

        self.window._on_window_map()

        self.assertEqual(self.window.root.calls, [])


if __name__ == "__main__":
    unittest.main()
