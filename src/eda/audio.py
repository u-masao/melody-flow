import os
import subprocess

import mido
from pydub import AudioSegment

# --- 1. MIDIファイルの作成 (mido) ---
# ファイル名を設定
midi_filename = "data/interim/sample.mid"
wav_filename = "data/interim/output.wav"
mp3_filename = "data/interim/output.mp3"
soundfont = "data/raw/FluidR3_GM.sf2"

# MIDIトラックを作成
track = mido.MidiTrack()

# ノートを追加 (C4, D4, E4, F4, G4)
# note_on:  channel, note, velocity, time
# note_off: channel, note, velocity, time
track.append(mido.Message("program_change", program=1, time=0))  # ピアノ音色に設定
track.append(mido.Message("note_on", note=60, velocity=64, time=480))  # C4
track.append(mido.Message("note_off", note=60, velocity=64, time=480))
track.append(mido.Message("note_on", note=62, velocity=64, time=0))  # D4
track.append(mido.Message("note_off", note=62, velocity=64, time=480))
track.append(mido.Message("note_on", note=64, velocity=64, time=0))  # E4
track.append(mido.Message("note_off", note=64, velocity=64, time=480))
track.append(mido.Message("note_on", note=65, velocity=64, time=0))  # F4
track.append(mido.Message("note_off", note=65, velocity=64, time=480))
track.append(mido.Message("note_on", note=67, velocity=64, time=0))  # G4
track.append(mido.Message("note_off", note=67, velocity=64, time=480))

# MIDIファイルとして保存
mid = mido.MidiFile()
mid.tracks.append(track)
mid.save(midi_filename)
print(f"✅ MIDIファイル '{midi_filename}' を作成しました。")


# ファイル名とサウンドフォントを設定
if not os.path.exists(soundfont):
    print(f"⚠️ サウンドフォントファイル '{soundfont}' が見つかりません。")
else:
    # FluidSynth cli を使ってMIDIをWavに変換
    gain = 0.75
    sampling_rate = 44100

    stdout = subprocess.DEVNULL
    subprocess.call(
        [
            "fluidsynth",
            "-ni",
            "-g",
            str(gain),
            soundfont,
            midi_filename,
            "-F",
            wav_filename,
            "-r",
            str(sampling_rate),
        ],
        stdout=stdout,
    )
    print(f"✅ Wavファイル '{wav_filename}' を作成しました。")

    # --- 3. MP3ファイルへの変換 (pydub) ---

    # Wavファイルを読み込み
    sound = AudioSegment.from_wav(wav_filename)

    # 音量を10デシベル上げる
    sound = sound + 10

    # MP3ファイルとしてエクスポート
    sound.export(mp3_filename, format="mp3")
    print(f"✅ MP3ファイル '{mp3_filename}' を作成しました。")
