"""
Unit tests for frame orientation and rotation transforms.
"""

import unittest
import numpy as np
from camera.orientation import (
    normalize_angle,
    rotate_frame,
    flip_frame,
    cycle_rotation,
    VALID_ROTATION_ANGLES
)


class TestOrientation(unittest.TestCase):

    def test_normalize_angle(self):
        self.assertEqual(normalize_angle(0), 0)
        self.assertEqual(normalize_angle(90), 90)
        self.assertEqual(normalize_angle(180), 180)
        self.assertEqual(normalize_angle(270), 270)
        self.assertEqual(normalize_angle(360), 0)
        self.assertEqual(normalize_angle(450), 90)
        self.assertEqual(normalize_angle(-90), 270)

    def test_rotate_dimensions(self):
        # 480 height x 640 width
        test_img = np.zeros((480, 640, 3), dtype=np.uint8)

        rot_0 = rotate_frame(test_img, 0)
        self.assertEqual(rot_0.shape, (480, 640, 3))

        rot_90 = rotate_frame(test_img, 90)
        self.assertEqual(rot_90.shape, (640, 480, 3))  # Width and height swapped

        rot_180 = rotate_frame(test_img, 180)
        self.assertEqual(rot_180.shape, (480, 640, 3))

        rot_270 = rotate_frame(test_img, 270)
        self.assertEqual(rot_270.shape, (640, 480, 3))  # Width and height swapped

    def test_cycle_rotation(self):
        self.assertEqual(cycle_rotation(0), 90)
        self.assertEqual(cycle_rotation(90), 180)
        self.assertEqual(cycle_rotation(180), 270)
        self.assertEqual(cycle_rotation(270), 0)

    def test_flip_frame(self):
        test_img = np.arange(12, dtype=np.uint8).reshape((3, 4))
        h_flipped = flip_frame(test_img, horizontal=True)
        self.assertEqual(h_flipped.shape, test_img.shape)
        np.testing.assert_array_equal(h_flipped[:, 0], test_img[:, -1])


if __name__ == "__main__":
    unittest.main()
