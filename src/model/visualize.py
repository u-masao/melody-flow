import io
import matplotlib.pyplot as plt
import pretty_midi
from typing import Any
from PIL import Image
import weave  # weaveをインポート

# Pillowをインストールする必要があります
# pip install Pillow


@weave.op()  # weave.opで関数を装飾
def create_pianoroll_image(parsed_notes: list[dict[str, Any]]) -> Image.Image | None:
    """
    パースされたノート情報からピアノロール画像を生成し、Pillow Imageオブジェクトとして返す。
    """
    if not parsed_notes:
        return None

    pm = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0)

    current_time = 0.0
    for note_info in parsed_notes:
        pitch = note_info["pitch"]
        duration_sec = note_info["duration"] / 1000.0
        wait_sec = note_info["wait"] / 1000.0
        velocity = note_info["velocity"]
        start_time = current_time + wait_sec
        end_time = start_time + duration_sec
        note = pretty_midi.Note(velocity=velocity, pitch=pitch, start=start_time, end=end_time)
        instrument.notes.append(note)
        current_time = start_time

    pm.instruments.append(instrument)

    fig, ax = plt.subplots(figsize=(12, 6))
    pianoroll = pm.get_piano_roll(fs=100)

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

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    # バイト列からPillow Imageオブジェクトを作成して返す
    return Image.open(buf)
