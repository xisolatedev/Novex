import unittest

from controller.keyboard import KeyboardState, map_keys_to_axes, MANUAL_THROTTLE_STEP


class TestKeyboardState(unittest.TestCase):
    def test_press_release_and_case(self):
        kb = KeyboardState()
        self.assertTrue(kb.press("W"))
        self.assertTrue(kb.press("Left"))
        self.assertEqual(kb.held(), frozenset({"w", "Left"}))
        kb.release("w")
        self.assertEqual(kb.held(), frozenset({"Left"}))

    def test_non_flight_keys_ignored(self):
        kb = KeyboardState()
        self.assertFalse(kb.press("x"))
        self.assertEqual(kb.held(), frozenset())

    def test_release_all(self):
        kb = KeyboardState()
        for k in ("w", "a", "Up", "Right"):
            kb.press(k)
        kb.release_all()
        self.assertEqual(kb.held(), frozenset())

    def test_held_key_persists_across_ticks(self):
        kb = KeyboardState()
        kb.press("d")
        first = map_keys_to_axes(kb.held(), 40, True).axes
        second = map_keys_to_axes(kb.held(), 40, True).axes
        self.assertEqual(first.roll, 168)
        self.assertEqual(first, second)
        kb.release("d")
        self.assertEqual(map_keys_to_axes(kb.held(), 40, True).axes.roll, 128)


class TestMapping(unittest.TestCase):
    def test_fixed_height_throttle_springs_back(self):
        self.assertEqual(map_keys_to_axes(frozenset({"Up"}), 40, True).axes.throttle, 255)
        self.assertEqual(map_keys_to_axes(frozenset(), 40, True).axes.throttle, 128)

    def test_manual_throttle_ramps_and_holds(self):
        m = map_keys_to_axes(frozenset({"Up"}), 40, False, manual_throttle=0)
        self.assertEqual(m.axes.throttle, MANUAL_THROTTLE_STEP)
        held = map_keys_to_axes(frozenset(), 40, False, manual_throttle=m.manual_throttle)
        self.assertEqual(held.axes.throttle, MANUAL_THROTTLE_STEP)
        down = map_keys_to_axes(frozenset({"Down"}), 40, False, manual_throttle=5)
        self.assertEqual(down.axes.throttle, 0)

    def test_power_levels(self):
        for half, expected in ((40, 168), (60, 188), (127, 255)):
            self.assertEqual(map_keys_to_axes(frozenset({"w"}), half, True).axes.pitch, expected)

    def test_yaw_uses_full_left_stick(self):
        self.assertEqual(map_keys_to_axes(frozenset({"Left"}), 40, True).axes.yaw, 1)
        self.assertEqual(map_keys_to_axes(frozenset({"Right"}), 40, True).axes.yaw, 255)


if __name__ == "__main__":
    unittest.main()
