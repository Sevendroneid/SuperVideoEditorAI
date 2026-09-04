import subprocess
from pathlib import Path

from app.ffmpeg import FFmpeg
from app.models import ClipEvidence
from app.segments import extract_segments
from app.story import build_baseline_story


def make_fixture(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=8000",
            "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(path),
        ], check=True,
    )


def test_full_analysis_to_render(tmp_path: Path) -> None:
    source = tmp_path / "fixture.mp4"
    make_fixture(source)
    ffmpeg = FFmpeg()
    probe = ffmpeg.probe(source)
    assert probe["streams"]
    format_data = probe.get("format", {})
    video = next(stream for stream in probe["streams"] if stream.get("codec_type") == "video")
    fps_text = video.get("avg_frame_rate", "0/0")
    numerator, denominator = (int(part) for part in fps_text.split("/", 1))
    fps = numerator / denominator if denominator else 0.0
    clip = ClipEvidence(
        path=str(source),
        filename=source.name,
        duration_seconds=float(format_data.get("duration", 0)),
        width=int(video.get("width", 0)),
        height=int(video.get("height", 0)),
        fps=fps,
        frame_count=int(video.get("nb_frames", 0) or 0),
        score=1.0,
        reasons=["synthetic E2E fixture"],
    )

    clips = extract_segments(source, clip)
    assert clips
    timeline = build_baseline_story(clips, max_duration=3.0)
    assert timeline.items

    rendered = []
    for index, item in enumerate(timeline.items):
        target = tmp_path / f"segment_{index}.mp4"
        ffmpeg.extract_segment(source, item.start_seconds, item.end_seconds, target)
        assert target.is_file() and target.stat().st_size > 0
        rendered.append(target)

    output = tmp_path / "output.mp4"
    ffmpeg.concat(rendered, output)
    assert output.is_file() and output.stat().st_size > 0
    result = ffmpeg.probe(output)
    video = next(stream for stream in result["streams"] if stream["codec_type"] == "video")
    assert float(video["duration"]) > 0
