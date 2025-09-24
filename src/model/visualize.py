import io
import matplotlib.pyplot as plt
import pretty_midi
from typing import Any


def create_pianoroll_image(parsed_notes: list[dict[str, Any]]) -> bytes | None:
    """
    パースされたノート情報からピアノロール画像を生成し、bytesとして返す。
    """
    if not parsed_notes:
        return None

    pm = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0)  # 0: Acoustic Grand Piano

    current_time = 0.0
    for note_info in parsed_notes:
        pitch = note_info["pitch"]
        # durationとwaitはミリ秒と仮定し、秒に変換
        duration_sec = note_info["duration"] / 1000.0
        wait_sec = note_info["wait"] / 1000.0
        velocity = note_info["velocity"]

        start_time = current_time + wait_sec
        end_time = start_time + duration_sec

        note = pretty_midi.Note(velocity=velocity, pitch=pitch, start=start_time, end=end_time)
        instrument.notes.append(note)

        # 次のノートの開始時間を更新
        current_time = start_time

    pm.instruments.append(instrument)

    # Matplotlibでピアノロールを描画
    fig, ax = plt.subplots(figsize=(12, 6))
    pianoroll = pm.get_piano_roll(fs=100)

    # 描画範囲を実際のノート範囲に限定
    min_pitch = min(note.pitch for note in instrument.notes)
    max_pitch = max(note.pitch for note in instrument.notes)

    ax.imshow(
        pianoroll[min_pitch : max_pitch + 1],
        aspect="auto",
        origin="lower",
        extent=[0, pm.get_end_time(), min_pitch, max_pitch + 1],
        cmap="viridis",
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Pitch (MIDI Note Number)")
    ax.set_title("Generated Melody Pianoroll")
    plt.tight_layout()

    # 画像をメモリ上のバイナリデータとして保存
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    return buf.getvalue()
