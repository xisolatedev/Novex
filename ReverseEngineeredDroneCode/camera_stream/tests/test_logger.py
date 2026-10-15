"""
Unit tests for telemetry CSV logging.
"""

import os
import tempfile
import time
import unittest
from telemetry.logger import TelemetryLogger
from telemetry.model import DroneTelemetryPacket


class TestTelemetryLogger(unittest.TestCase):

    def test_csv_logging_and_flush(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            logger = TelemetryLogger(filepath=tmp_path, format_type="csv")
            logger.start()

            pkt = DroneTelemetryPacket(
                timestamp=time.time(),
                source_ip="192.168.1.1",
                raw_bytes=bytes([0x5A, 0x02, 0x4D, 0x01] + [0] * 16),
                length=20,
                device_id=90,
                is_gl_model=True,
                requires_rotation=True,
                camera_reset_mode=2,
                remote_trigger_raw=0x4D,
                remote_trigger_name="Photo Shutter",
                photo_sequence=1,
                unknown_bytes={19: "00"}
            )
            logger.log_packet(pkt)
            logger.stop()

            self.assertTrue(os.path.exists(tmp_path))
            with open(tmp_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Header + 1 record
            self.assertEqual(len(lines), 2)
            self.assertIn("timestamp_iso", lines[0])
            self.assertIn("5A 02 4D 01", lines[1])
            self.assertIn("Photo Shutter", lines[1])
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
