import unittest

import numpy as np
import pandas as pd

from backend.pipeline import FEATURES, prepare_live_features, prepare_training_features


RAW_FEATURES = {
    "duration": 2.5,
    "src_port": 50000,
    "dst_port": 1883,
    "proto": "tcp",
    "src_bytes": 300,
    "dst_bytes": 250,
    "src_pkts": 5,
    "dst_pkts": 5,
    "src_ip_bytes": 420,
    "dst_ip_bytes": 370,
}


class FeaturePipelineTests(unittest.TestCase):
    def test_live_and_training_transformations_match(self) -> None:
        live_values = prepare_live_features(RAW_FEATURES)
        training_values = prepare_training_features(
            pd.DataFrame([RAW_FEATURES], columns=FEATURES)
        )

        np.testing.assert_allclose(live_values, training_values)
        self.assertEqual(live_values.shape, (1, 10))
        self.assertEqual(live_values[0, 1], 50000)
        self.assertEqual(live_values[0, 2], 1883)
        self.assertEqual(live_values[0, 3], 1)
        self.assertAlmostEqual(live_values[0, 0], np.log1p(2.5))

    def test_numeric_protocol_ids_match_dataset_protocol_names(self) -> None:
        live_values = prepare_live_features({**RAW_FEATURES, "proto": 1})
        training_values = prepare_training_features(
            pd.DataFrame([RAW_FEATURES], columns=FEATURES)
        )

        np.testing.assert_allclose(live_values, training_values)

    def test_rejects_missing_extra_negative_and_unknown_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "Feature keys mismatch"):
            prepare_live_features(
                {
                    key: value
                    for key, value in RAW_FEATURES.items()
                    if key != "proto"
                }
            )
        with self.assertRaisesRegex(ValueError, "Feature keys mismatch"):
            prepare_live_features({**RAW_FEATURES, "extra": 1})
        with self.assertRaisesRegex(ValueError, "non-negative"):
            prepare_live_features({**RAW_FEATURES, "src_bytes": -1})
        with self.assertRaisesRegex(ValueError, "Unsupported protocol"):
            prepare_live_features({**RAW_FEATURES, "proto": "unknown"})


if __name__ == "__main__":
    unittest.main()
