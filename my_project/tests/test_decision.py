import unittest

from backend.decision import ConsecutiveDetectionPolicy


class ConsecutiveDetectionPolicyTests(unittest.TestCase):
    def test_blocks_only_after_required_repeated_detection(self) -> None:
        policy = ConsecutiveDetectionPolicy(0.9, 3)

        self.assertFalse(policy.observe("ESP-A", "dos", 0.95))
        self.assertFalse(policy.observe("ESP-A", "dos", 0.95))
        self.assertTrue(policy.observe("ESP-A", "dos", 0.95))

    def test_resets_on_normal_low_confidence_or_class_change(self) -> None:
        policy = ConsecutiveDetectionPolicy(0.9, 2)

        self.assertFalse(policy.observe("ESP-A", "dos", 0.95))
        self.assertFalse(policy.observe("ESP-A", "dos", 0.89))
        self.assertFalse(policy.observe("ESP-A", "dos", 0.95))
        self.assertFalse(policy.observe("ESP-A", "ddos", 0.95))
        self.assertFalse(policy.observe("ESP-A", "normal", 0.99))
        self.assertFalse(policy.observe("ESP-A", "dos", 0.95))
        self.assertTrue(policy.observe("ESP-A", "dos", 0.95))

    def test_tracks_devices_independently(self) -> None:
        policy = ConsecutiveDetectionPolicy(0.9, 2)

        self.assertFalse(policy.observe("ESP-A", "dos", 0.95))
        self.assertFalse(policy.observe("ESP-B", "dos", 0.95))
        self.assertTrue(policy.observe("ESP-A", "dos", 0.95))
        self.assertTrue(policy.observe("ESP-B", "dos", 0.95))


if __name__ == "__main__":
    unittest.main()
