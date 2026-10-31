"""Small, testable policy for repeated high-confidence detections."""


class ConsecutiveDetectionPolicy:
    def __init__(self, confidence_threshold: float = 0.90, required_count: int = 3):
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0 and 1")
        if required_count < 1:
            raise ValueError("required_count must be at least 1")
        self.confidence_threshold = confidence_threshold
        self.required_count = required_count
        self._last_class: dict[str, str] = {}
        self._counts: dict[str, int] = {}

    def observe(self, device_id: str, predicted_class: str, confidence: float) -> bool:
        """Return true once a malicious class meets the consecutive threshold."""
        if predicted_class == "normal" or confidence < self.confidence_threshold:
            self.reset(device_id)
            return False

        if self._last_class.get(device_id) == predicted_class:
            self._counts[device_id] = self._counts.get(device_id, 0) + 1
        else:
            self._last_class[device_id] = predicted_class
            self._counts[device_id] = 1
        return self._counts[device_id] >= self.required_count

    def reset(self, device_id: str) -> None:
        self._last_class.pop(device_id, None)
        self._counts.pop(device_id, None)
