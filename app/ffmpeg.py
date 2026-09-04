import json
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


class FFmpeg:
    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe") -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin

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
        result = self._run([
            self.ffprobe_bin, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)
        ], timeout=60)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise FFmpegError("ffprobe returned invalid JSON") from exc

    def concat(self, inputs: list[Path], output: Path) -> Path:
        if not inputs:
            raise FFmpegError("At least one input clip is required")
        output.parent.mkdir(parents=True, exist_ok=True)
        list_file = output.with_suffix(".concat.txt")
        try:
            lines = []
            for item in inputs:
                resolved = item.resolve()
                lines.append("file '" + str(resolved).replace("'", "'\\''") + "'")
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
