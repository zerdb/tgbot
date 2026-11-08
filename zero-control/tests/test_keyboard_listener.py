"""Тесты обработки правых Ctrl/Shift без установки системного Windows hook."""
import unittest

from keyboard_listener import (
    KeyboardListener,
    VK_RCONTROL,
    VK_RSHIFT,
    WM_KEYDOWN,
    WM_KEYUP,
)


class KeyboardListenerTests(unittest.TestCase):
    def setUp(self):
        self.state = {"recording": False, "mode": None}
        self.calls = []

        def start_recording(mode):
            if self.state["recording"]:
                return
            self.state.update(recording=True, mode=mode)
            self.calls.append(("start", mode))

        def promote_to_dictation():
            if self.state["recording"] and self.state["mode"] != "text":
                self.state["mode"] = "text"
                self.calls.append(("promote",))

        def stop_recording():
            if self.state["recording"]:
                self.state.update(recording=False, mode=None)
                self.calls.append(("stop",))

        self.listener = KeyboardListener(
            start_recording,
            promote_to_dictation,
            stop_recording,
            lambda: self.state["recording"] and self.state["mode"] == "text",
        )

    def send(self, key, event):
        self.listener._events.put((key, event))
        self.listener.process_events()

    def test_right_ctrl_starts_command_and_shift_promotes_to_dictation(self):
        self.send(VK_RCONTROL, WM_KEYDOWN)
        self.send(VK_RSHIFT, WM_KEYDOWN)
        self.send(VK_RSHIFT, WM_KEYUP)
        self.send(VK_RCONTROL, WM_KEYUP)

        self.assertEqual(
            self.calls,
            [("start", "command"), ("promote",), ("stop",)],
        )

    def test_shift_held_before_ctrl_starts_dictation(self):
        self.send(VK_RSHIFT, WM_KEYDOWN)
        self.send(VK_RCONTROL, WM_KEYDOWN)
        self.send(VK_RSHIFT, WM_KEYUP)
        self.send(VK_RCONTROL, WM_KEYUP)

        self.assertEqual(self.calls, [("start", "text"), ("stop",)])

    def test_repeated_keydown_does_not_start_recording_twice(self):
        self.send(VK_RCONTROL, WM_KEYDOWN)
        self.send(VK_RCONTROL, WM_KEYDOWN)
        self.send(VK_RCONTROL, WM_KEYUP)

        self.assertEqual(self.calls, [("start", "command"), ("stop",)])


if __name__ == "__main__":
    unittest.main()
