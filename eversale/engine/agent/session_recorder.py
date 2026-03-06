"""
Session GIF Recorder for browser automation debugging.

Records browser sessions as animated GIFs with annotations and timestamps.
Inspired by browser-use's recording feature but optimized for our architecture.
"""

import os
import json
import asyncio
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal
from dataclasses import dataclass, asdict
from io import BytesIO
import logging

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise ImportError("PIL (Pillow) is required. Install with: pip install Pillow")

logger = logging.getLogger(__name__)

RecordingMode = Literal["FULL", "ACTIONS", "ERRORS", "MANUAL"]

@dataclass
class FrameMetadata:
    """Metadata for a single frame."""
    frame_number: int
    timestamp: str
    annotation: str
    is_marker: bool = False
    marker_name: Optional[str] = None


@dataclass
class RecordingMetadata:
    """Metadata for an entire recording session."""
    session_id: str
    mode: RecordingMode
    started_at: str
    ended_at: Optional[str] = None
    total_frames: int = 0
    frame_rate: int = 2
    markers: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.markers is None:
            self.markers = []


class SessionRecorder:
    """
    Records browser sessions as animated GIFs.

    Features:
    - Multiple recording modes (FULL, ACTIONS, ERRORS, MANUAL)
    - Screenshot capture with annotations
    - Visual markers for key events
    - Metadata tracking with timing info
    - Memory-efficient frame management

    Usage:
        recorder = get_recorder()
        recorder.start_recording("session_123", mode="ACTIONS")
        await recorder.capture_frame(screenshot_bytes, "Clicking login button")
        recorder.add_marker("login_complete")
        gif_path = await recorder.stop_recording()
    """

    def __init__(self, base_dir: str = "memory/recordings", max_frames: int = 500):
        self.base_dir = Path(base_dir)
        self.max_frames = max_frames

        # Recording state
        self.is_recording = False
        self.session_id: Optional[str] = None
        self.mode: Optional[RecordingMode] = None
        self.frames: List[FrameMetadata] = []
        self.frame_count = 0
        self.started_at: Optional[datetime] = None

        # Paths
        self.session_dir: Optional[Path] = None
        self.frames_dir: Optional[Path] = None

        # Settings
        self.frame_rate = 2  # frames per second in output GIF
        self.frame_duration = 500  # milliseconds per frame

        logger.info(f"SessionRecorder initialized (max_frames={max_frames})")

    def start_recording(self, session_id: str, mode: RecordingMode = "ACTIONS") -> None:
        """
        Start a new recording session.

        Args:
            session_id: Unique identifier for this session
            mode: Recording mode (FULL, ACTIONS, ERRORS, MANUAL)
        """
        if self.is_recording:
            logger.warning(f"Already recording session {self.session_id}. Stopping previous recording.")
            asyncio.create_task(self.stop_recording())

        self.session_id = session_id
        self.mode = mode
        self.started_at = datetime.utcnow()
        self.frames = []
        self.frame_count = 0
        self.is_recording = True

        # Setup directories
        self.session_dir = self.base_dir / session_id
        self.frames_dir = self.session_dir / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Recording started: session={session_id}, mode={mode}, dir={self.session_dir}")

    async def capture_frame(
        self,
        screenshot_data: bytes,
        annotation: str = "",
        force: bool = False
    ) -> bool:
        """
        Capture a single frame with optional annotation.

        Args:
            screenshot_data: Raw screenshot bytes (PNG/JPEG)
            annotation: Text annotation to add to the frame
            force: Force capture regardless of recording mode

        Returns:
            True if frame was captured, False otherwise
        """
        if not self.is_recording:
            logger.debug("Not recording, skipping frame capture")
            return False

        if not force and not self._should_capture():
            return False

        if self.frame_count >= self.max_frames:
            logger.warning(f"Max frames ({self.max_frames}) reached. Skipping frame.")
            return False

        try:
            # Save frame to disk
            frame_path = self.frames_dir / f"frame_{self.frame_count:04d}.png"

            # Load image and add annotation
            image = Image.open(BytesIO(screenshot_data))

            # Add annotation overlay if provided
            if annotation:
                image = self._add_annotation(image, annotation)

            # Save frame
            image.save(frame_path, "PNG")

            # Store metadata
            frame_meta = FrameMetadata(
                frame_number=self.frame_count,
                timestamp=datetime.utcnow().isoformat(),
                annotation=annotation
            )
            self.frames.append(frame_meta)

            self.frame_count += 1
            logger.debug(f"Frame captured: {frame_path} (annotation: {annotation})")

            return True

        except Exception as e:
            logger.error(f"Error capturing frame: {e}", exc_info=True)
            return False

    def add_marker(self, name: str) -> None:
        """
        Add a visual marker to the recording.

        Markers are special frames that highlight key events.

        Args:
            name: Name/label for the marker
        """
        if not self.is_recording:
            logger.debug("Not recording, skipping marker")
            return

        marker_meta = FrameMetadata(
            frame_number=self.frame_count,
            timestamp=datetime.utcnow().isoformat(),
            annotation=f"MARKER: {name}",
            is_marker=True,
            marker_name=name
        )
        self.frames.append(marker_meta)

        logger.info(f"Marker added: {name} at frame {self.frame_count}")

    async def stop_recording(self) -> Optional[str]:
        """
        Stop recording and generate the final GIF.

        Returns:
            Path to the generated GIF, or None if recording failed
        """
        if not self.is_recording:
            logger.warning("No active recording to stop")
            return None

        self.is_recording = False
        ended_at = datetime.utcnow()

        try:
            # Save metadata
            metadata = RecordingMetadata(
                session_id=self.session_id,
                mode=self.mode,
                started_at=self.started_at.isoformat(),
                ended_at=ended_at.isoformat(),
                total_frames=self.frame_count,
                frame_rate=self.frame_rate,
                markers=[asdict(f) for f in self.frames if f.is_marker]
            )

            metadata_path = self.session_dir / "metadata.json"
            with open(metadata_path, "w") as f:
                json.dump(asdict(metadata), f, indent=2)

            logger.info(f"Metadata saved: {metadata_path}")

            # Generate GIF
            gif_path = await self._generate_gif()

            if gif_path:
                logger.info(f"Recording complete: {gif_path} ({self.frame_count} frames)")

            # Cleanup
            self._reset_state()

            return str(gif_path) if gif_path else None

        except Exception as e:
            logger.error(f"Error stopping recording: {e}", exc_info=True)
            self._reset_state()
            return None

    def get_recording_status(self) -> Dict[str, Any]:
        """
        Get current recording status.

        Returns:
            Dictionary with recording status information
        """
        return {
            "is_recording": self.is_recording,
            "session_id": self.session_id,
            "mode": self.mode,
            "frame_count": self.frame_count,
            "max_frames": self.max_frames,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "markers": [f.marker_name for f in self.frames if f.is_marker]
        }

    async def capture_frame_base64(self, screenshot_base64: str, annotation: str = "") -> bool:
        """
        Capture frame from base64-encoded screenshot.

        Args:
            screenshot_base64: Base64-encoded screenshot data
            annotation: Text annotation to add to the frame

        Returns:
            True if frame was captured, False otherwise
        """
        try:
            # Remove data URL prefix if present
            if "," in screenshot_base64:
                screenshot_base64 = screenshot_base64.split(",", 1)[1]

            screenshot_bytes = base64.b64decode(screenshot_base64)
            return await self.capture_frame(screenshot_bytes, annotation)
        except Exception as e:
            logger.error(f"Error decoding base64 screenshot: {e}")
            return False

    # Private methods

    def _should_capture(self) -> bool:
        """Determine if current frame should be captured based on mode."""
        # MANUAL mode requires explicit force=True
        if self.mode == "MANUAL":
            return False

        # FULL mode captures everything
        if self.mode == "FULL":
            return True

        # ACTIONS and ERRORS modes are controlled by caller
        # (caller decides when to call capture_frame)
        return True

    def _add_annotation(self, image: Image.Image, annotation: str) -> Image.Image:
        """
        Add text annotation overlay to image.

        Args:
            image: PIL Image object
            annotation: Text to overlay

        Returns:
            Modified PIL Image object
        """
        try:
            # Create a copy to avoid modifying original
            annotated = image.copy()
            draw = ImageDraw.Draw(annotated)

            # Try to use a nice font, fallback to default
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
            except:
                font = ImageFont.load_default()

            # Get text size for background rectangle
            bbox = draw.textbbox((0, 0), annotation, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # Position at bottom of image
            img_width, img_height = annotated.size
            x = 10
            y = img_height - text_height - 15

            # Draw semi-transparent background
            padding = 5
            draw.rectangle(
                [(x - padding, y - padding),
                 (x + text_width + padding, y + text_height + padding)],
                fill=(0, 0, 0, 180)
            )

            # Draw text
            draw.text((x, y), annotation, fill=(255, 255, 255), font=font)

            # Add timestamp in top-right
            timestamp = datetime.utcnow().strftime("%H:%M:%S")
            ts_bbox = draw.textbbox((0, 0), timestamp, font=font)
            ts_width = ts_bbox[2] - ts_bbox[0]
            draw.rectangle(
                [(img_width - ts_width - 15, 5),
                 (img_width - 5, text_height + 10)],
                fill=(0, 0, 0, 180)
            )
            draw.text((img_width - ts_width - 10, 8), timestamp, fill=(255, 255, 255), font=font)

            return annotated

        except Exception as e:
            logger.error(f"Error adding annotation: {e}")
            return image

    async def _generate_gif(self) -> Optional[Path]:
        """
        Generate animated GIF from captured frames.

        Returns:
            Path to generated GIF, or None if failed
        """
        if self.frame_count == 0:
            logger.warning("No frames to generate GIF")
            return None

        try:
            output_path = self.session_dir / "output.gif"

            # Load all frames
            frames = []
            for i in range(self.frame_count):
                frame_path = self.frames_dir / f"frame_{i:04d}.png"
                if frame_path.exists():
                    img = Image.open(frame_path)
                    # Convert to RGB if necessary (GIF doesn't support RGBA well)
                    if img.mode == "RGBA":
                        rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                        rgb_img.paste(img, mask=img.split()[3] if len(img.split()) == 4 else None)
                        frames.append(rgb_img)
                    else:
                        frames.append(img.convert("RGB"))

            if not frames:
                logger.error("No valid frames found")
                return None

            # Save as GIF
            frames[0].save(
                output_path,
                save_all=True,
                append_images=frames[1:],
                duration=self.frame_duration,
                loop=0,
                optimize=True
            )

            logger.info(f"GIF generated: {output_path} ({len(frames)} frames)")
            return output_path

        except Exception as e:
            logger.error(f"Error generating GIF: {e}", exc_info=True)
            return None

    def _reset_state(self) -> None:
        """Reset recorder state after stopping."""
        self.is_recording = False
        self.session_id = None
        self.mode = None
        self.frames = []
        self.frame_count = 0
        self.started_at = None
        self.session_dir = None
        self.frames_dir = None


# Singleton instance
_recorder_instance: Optional[SessionRecorder] = None


def get_recorder(base_dir: str = "memory/recordings", max_frames: int = 500) -> SessionRecorder:
    """
    Get the singleton SessionRecorder instance.

    Args:
        base_dir: Base directory for recordings
        max_frames: Maximum number of frames to capture

    Returns:
        SessionRecorder instance
    """
    global _recorder_instance

    if _recorder_instance is None:
        _recorder_instance = SessionRecorder(base_dir=base_dir, max_frames=max_frames)

    return _recorder_instance


# Test function
async def _test_recorder():
    """Test the session recorder with synthetic data."""
    print("Testing SessionRecorder...")

    recorder = get_recorder(base_dir="memory/recordings_test", max_frames=10)

    # Start recording
    recorder.start_recording("test_session_001", mode="ACTIONS")
    print(f"Recording started: {recorder.get_recording_status()}")

    # Create some test frames
    for i in range(5):
        # Create a simple test image
        img = Image.new("RGB", (800, 600), color=(100 + i * 30, 150, 200))
        draw = ImageDraw.Draw(img)
        draw.text((50, 50), f"Test Frame {i + 1}", fill=(255, 255, 255))

        # Convert to bytes
        img_bytes = BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        # Capture frame
        captured = await recorder.capture_frame(
            img_bytes.read(),
            annotation=f"Test action {i + 1}"
        )
        print(f"Frame {i + 1} captured: {captured}")

        # Add a marker at frame 3
        if i == 2:
            recorder.add_marker("midpoint")

        await asyncio.sleep(0.1)

    # Check status
    status = recorder.get_recording_status()
    print(f"Recording status: {status}")

    # Stop recording and generate GIF
    gif_path = await recorder.stop_recording()
    print(f"Recording stopped. GIF saved to: {gif_path}")

    if gif_path and os.path.exists(gif_path):
        print("Test PASSED: GIF file created successfully")

        # Check metadata
        metadata_path = os.path.join(os.path.dirname(gif_path), "metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path, "r") as f:
                metadata = json.load(f)
                print(f"Metadata: {json.dumps(metadata, indent=2)}")
    else:
        print("Test FAILED: GIF file not created")


if __name__ == "__main__":
    # Run test
    asyncio.run(_test_recorder())
