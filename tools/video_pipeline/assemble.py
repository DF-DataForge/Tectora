"""Raw screen recording + voice clips → final MP4, subtitles and thumbnail."""

import os
import re
import subprocess
import wave

FADE = 0.4


def _fmt_srt(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_voice_track(shots, t0, total, path):
    """One WAV with every shot's clip at its place on the timeline."""
    clips = [s for s in shots if s["voice"]]
    if not clips:
        return None
    with wave.open(clips[0]["voice"]) as first:
        params = first.getparams()
    rate, width, channels = params.framerate, params.sampwidth, params.nchannels
    frame = width * channels
    track = bytearray(int(total * rate) * frame)
    for shot in clips:
        with wave.open(shot["voice"]) as clip:
            data = clip.readframes(clip.getnframes())
        offset = int((shot["voice_start"] - t0) * rate) * frame
        data = data[: max(len(track) - offset, 0)]
        track[offset:offset + len(data)] = data
    with wave.open(path, "wb") as out:
        out.setparams(params)
        out.writeframes(bytes(track))
    return path


def write_srt(shots, t0, path, max_chars=84):
    """Subtitles from the voice-over, sentence by sentence.

    A shot's clip is split over its sentences in proportion to their length,
    which is close enough for one voice at one tempo.
    """
    cues = []
    for shot in shots:
        if not shot["voice"]:
            continue
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", shot["voice_over"]) if s]
        # Glue short sentences together so a cue is never a lone "Startpunt één: CRM."
        merged = []
        for sentence in sentences:
            if merged and len(merged[-1]) + len(sentence) < max_chars:
                merged[-1] += " " + sentence
            else:
                merged.append(sentence)
        total_chars = sum(len(s) for s in merged)
        cursor = shot["voice_start"] - t0
        for sentence in merged:
            span = shot["voice_duration"] * len(sentence) / total_chars
            cues.append((cursor, cursor + span, sentence))
            cursor += span
    with open(path, "w", encoding="utf-8") as handle:
        for n, (start, end, text) in enumerate(cues, 1):
            handle.write(f"{n}\n{_fmt_srt(start)} --> {_fmt_srt(end)}\n{text}\n\n")
    return path


def assemble(meta, out_dir, name, music=None, music_volume=0.18, thumbnail_shot=None):
    shots = meta["shots"]
    t0 = shots[0]["start"]
    total = shots[-1]["end"] - t0
    offset = t0 - meta["video_start"]
    if offset < 0:
        raise SystemExit("recording started after the first shot; timeline is unusable")

    voice = build_voice_track(shots, t0, total, os.path.join(out_dir, "voice.wav"))
    mp4 = os.path.join(out_dir, f"{name}.mp4")

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{offset:.3f}", "-t", f"{total:.3f}",
           "-i", meta["video"]]
    vf = (f"fade=t=in:st=0:d={FADE},fade=t=out:st={total - FADE:.3f}:d={FADE},"
          "scale=1920:1080:flags=lanczos,format=yuv420p")
    inputs = 1
    if voice:
        cmd += ["-i", voice]
        inputs += 1
    if music:
        cmd += ["-stream_loop", "-1", "-i", music]
        inputs += 1
    if voice and music:
        # Music ducks under the voice-over (sidechain), as in the script README.
        af = (f"[2:a]volume={music_volume},atrim=0:{total:.3f}[m];"
              "[1:a]asplit=2[v][sc];"
              "[m][sc]sidechaincompress=threshold=0.015:ratio=10:attack=20:release=500[duck];"
              f"[v][duck]amix=inputs=2:normalize=0,afade=t=out:st={total - 1:.3f}:d=1[a]")
        cmd += ["-filter_complex", af, "-map", "0:v", "-map", "[a]"]
    elif voice:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-r", "30",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart",
            "-t", f"{total:.3f}", mp4]
    subprocess.run(cmd, check=True)

    srt = write_srt(shots, t0, os.path.join(out_dir, f"{name}.srt"))

    thumb_at = 1.0
    for shot in shots:
        if shot["shot"] == thumbnail_shot:
            thumb_at = (shot["start"] + shot["end"]) / 2 - t0
    thumb = os.path.join(out_dir, f"{name}.jpg")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{thumb_at:.2f}", "-i", mp4,
                    "-frames:v", "1", "-q:v", "3", thumb], check=True)
    return {"video": mp4, "subtitles": srt, "thumbnail": thumb, "duration": total}
