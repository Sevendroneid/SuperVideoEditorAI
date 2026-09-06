import json
import re
import shutil
import subprocess
from pathlib import Path

try:
    import imageio_ffmpeg
except ImportError:  # pragma: no cover - dependency is pinned in requirements.txt
    imageio_ffmpeg = None


class FFmpegError(RuntimeError):
    pass


class FFmpeg:
    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe") -> None:
        self.ffmpeg_bin = self._resolve_ffmpeg(ffmpeg_bin)
        self.ffprobe_bin = shutil.which(ffprobe_bin) or ffprobe_bin
        self._system_ffprobe = bool(shutil.which(ffprobe_bin))

    @staticmethod
    def _resolve_ffmpeg(binary: str) -> str:
        configured = shutil.which(binary)
        if configured:
            return configured
        if imageio_ffmpeg is not None:
            try:
                return imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                pass
        return binary

    def _run(self, args: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        except FileNotFoundError as exc:
            raise FFmpegError(f"Executable not found: {args[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise FFmpegError(f"Command timed out after {timeout}s") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown ffmpeg error").strip()
            raise FFmpegError(detail[-4000:])
        return result

    def probe(self, path: Path) -> dict:
        if self._system_ffprobe:
            result = self._run([
                self.ffprobe_bin, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)
            ], timeout=60)
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise FFmpegError("ffprobe returned invalid JSON") from exc

        # Render's native Python runtime does not guarantee a system ffprobe.
        # imageio-ffmpeg bundles a portable ffmpeg binary, so derive the small
        # metadata subset used by the analyzer directly from `ffmpeg -i`.
        result = subprocess.run(
            [self.ffmpeg_bin, "-hide_banner", "-i", str(path)],
            capture_output=True, text=True, timeout=60, check=False,
        )
        diagnostic = result.stderr or result.stdout or ""
        if not diagnostic:
            raise FFmpegError("ffmpeg returned no media metadata")

        duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", diagnostic)
        duration = 0.0
        if duration_match:
            hours, minutes, seconds = duration_match.groups()
            duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)

        video_match = re.search(
            r"Stream #\S+(?:\([^)]*\))?:\s*Video:\s*([^,\n]+).*?(\d{2,5})x(\d{2,5})(?:[,\s].*?)?(?:,\s*([0-9]+(?:\.[0-9]+)?)\s*fps)?",
            diagnostic,
            re.IGNORECASE | re.DOTALL,
        )
        if not video_match:
            raise FFmpegError(f"No video stream found in {path.name}")

        codec, width, height, fps = video_match.groups()
        fps_value = float(fps) if fps else 0.0
        return {
            "format": {"duration": str(duration)},
            "streams": [{
                "codec_type": "video",
                "codec_name": codec.strip().split()[0],
                "width": int(width),
                "height": int(height),
                "avg_frame_rate": f"{fps_value}/1" if fps_value else "0/1",
                "duration": str(duration),
                "nb_frames": "0",
            }],
        }

    def extract_segment(self, input_path: Path, start: float, end: float, output: Path) -> Path:
        if start < 0 or end <= start:
            raise FFmpegError("Invalid segment boundaries")
        output.parent.mkdir(parents=True, exist_ok=True)
        self._run([
            self.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}", "-i", str(input_path), "-t", f"{end - start:.3f}",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-movflags", "+faststart", str(output)
        ], timeout=1200)
        return output

    def concat(self, inputs: list[Path], output: Path) -> Path:
        if not inputs:
            raise FFmpegError("At least one input clip is required")
        output.parent.mkdir(parents=True, exist_ok=True)
        list_file = output.with_suffix(".concat.txt")
        try:
            lines = ["file '" + str(item.resolve()).replace("'", "'\\''") + "'" for item in inputs]
            list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self._run([
                self.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "aac", "-movflags", "+faststart", str(output)
            ], timeout=1800)
        finally:
            list_file.unlink(missing_ok=True)
        return output
