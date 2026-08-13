#!/usr/bin/env python3
"""SRA TTS node with conversational and replaceable alert speech queues.

Subscribes to:
  - /sra/tts/speak  (String, plain text): normal conversational FIFO speech.
  - /sra/tts/alert  (String, JSON): keyed alert speech whose pending message may
    be replaced or cleared before playback.

The alert channel prevents repeated industrial warnings, such as successive
camera inspection failures, from accumulating stale speech in the queue.
"""

import json
import os
import queue
import subprocess
import tempfile
import threading
from collections import OrderedDict

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

VOICES_DIR = os.getenv("SRA_PIPER_VOICES_DIR", "")
ES_MODEL = os.getenv("SRA_PIPER_ES_MODEL", "es_ES-sharvard-medium.onnx")


class TTSNode(Node):

    def __init__(self):
        super().__init__("sra_tts_node")

        self.speak_queue: "queue.Queue[str]" = queue.Queue()
        self._alert_lock = threading.Lock()
        self._pending_alerts: "OrderedDict[str, str]" = OrderedDict()

        self.create_subscription(String, "/sra/tts/speak", self.on_speak, 10)
        self.create_subscription(String, "/sra/tts/alert", self.on_alert, 10)

        self.speaking_pub = self.create_publisher(Bool, "/sra/tts/speaking", 10)

        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

        self.get_logger().info(f"TTS node ready. Voices dir: {VOICES_DIR}")

    def on_speak(self, msg: String):
        """Append ordinary conversational speech in FIFO order."""
        text = msg.data.strip()
        if text:
            self.speak_queue.put(text)

    def on_alert(self, msg: String):
        """Replace or clear pending speech for one alert key."""
        try:
            payload = json.loads(msg.data)
            if not isinstance(payload, dict):
                raise ValueError("TTS alert must be a JSON object")

            key = str(payload.get("key", "")).strip()
            if not key:
                raise ValueError("TTS alert requires a key")

            active = payload.get("active", True)
            if not isinstance(active, bool):
                raise ValueError("TTS alert active must be boolean")

            text = str(payload.get("text", "")).strip()
            with self._alert_lock:
                if not active:
                    self._pending_alerts.pop(key, None)
                    return
                if not text:
                    raise ValueError("Active TTS alert requires text")

                # Preserve the original queue position for an existing key while
                # replacing its pending content with the newest message.
                self._pending_alerts[key] = text

        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.get_logger().warning(f"Rejected TTS alert: {exc}")

    def _worker_loop(self):
        while rclpy.ok():  # type: ignore[attr-defined]
            text = self._next_text()
            if text is None:
                continue
            self._speak(text)

    def _next_text(self) -> str | None:
        """Prioritize pending keyed alerts, then normal conversational speech."""
        with self._alert_lock:
            if self._pending_alerts:
                _, text = self._pending_alerts.popitem(last=False)
                return text

        try:
            return self.speak_queue.get(timeout=0.25)
        except queue.Empty:
            return None

    def _speak(self, text: str):
        model_path = os.path.join(VOICES_DIR, ES_MODEL)

        if not os.path.exists(model_path):
            self.get_logger().error(f"Piper model not found: {model_path}")
            return

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        try:
            subprocess.run(
                ["piper", "--model", model_path, "--output_file", wav_path],
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
                timeout=15,
            )

            self._publish_speaking(True)
            try:
                subprocess.run(["aplay", wav_path], check=True)
            finally:
                self._publish_speaking(False)

        except subprocess.CalledProcessError as exc:
            self.get_logger().error(f"Piper/aplay failed: {exc}")
        except subprocess.TimeoutExpired:
            self.get_logger().error("TTS synthesis/playback timed out")
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    def _publish_speaking(self, speaking: bool) -> None:
        msg = Bool()
        msg.data = speaking
        self.speaking_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = TTSNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
