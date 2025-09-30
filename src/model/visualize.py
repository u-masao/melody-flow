import io
import matplotlib.pyplot as plt
import pretty_midi
from typing import Any
from PIL import Image
import weave  # weaveをインポート
import base64
from matplotlib.ticker import MultipleLocator

# Pillowをインストールする必要があります
# pip install Pillow


@weave.op()
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


def plot_melodies(cache: dict):
    """
    ノートをプロットする関数。
    x軸を非表示にし、y軸に12間隔の補助線を追加します。
    """
    chord_melodies = cache.get("chord_melodies", {})

    # プロットの準備
    fig, ax = plt.subplots(2, (1 + len(chord_melodies)) // 2, figsize=(8, 3), sharey=True)
    ax = ax.flatten()

    # 各コードごとにプロット
    for i, (chord, notes_base64) in enumerate(chord_melodies.items()):
        # データのデコード
        notes_str = base64.b64decode(notes_base64).decode()
        notes = [int(x.split(" ")[0]) for x in notes_str.split("\n") if x]

        # 散布図をプロット
        ax[i].plot(notes, marker=".", linestyle="")

        # y軸の範囲とタイトルを設定
        ax[i].set_ylim(12 * 4, 12 * 7)
        ax[i].set_title(chord)

        # x軸の目盛りとラベルを非表示にする
        ax[i].tick_params(axis="x", which="both", bottom=False, top=False, labelbottom=False)

        # y軸に12ごとの補助線（グリッド）を引く
        ax[i].yaxis.set_major_locator(MultipleLocator(12))
        ax[i].grid(which="major", axis="y", linestyle="--")

    fig.tight_layout()
    return fig
