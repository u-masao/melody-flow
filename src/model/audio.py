import subprocess
from pathlib import Path
from typing import List, Dict, Union

import mido
from loguru import logger
from pydub import AudioSegment

class AudioUtility:
    # __init__ と create_midi_file は変更なし
    
    def __init__(self, soundfont_path: Union[str, Path]):
        """AudioUtilityのインスタンスを初期化します。"""
        self.soundfont = Path(soundfont_path)
        if not self.soundfont.is_file():
            raise FileNotFoundError(f"サウンドフォントが見つかりません: {self.soundfont}")

    def create_midi_file(
        self,
        notes: List[Dict[str, int]],
        output_path: Union[str, Path],
        program: int = 1,
    ) -> Path:
        """
        ノート情報のリストからMIDIファイルを作成します。

        Args:
            notes: ノート情報を格納した辞書のリスト。各辞書のフォーマットは以下の通りです。
                - 'note' (int): MIDIノート番号 (例: 60 = C4)。必須。
                - 'duration' (int): 音の長さ (tick単位)。必須。
                - 'velocity' (int, optional): 音の強さ (0-127)。デフォルトは64。
            output_path: 出力MIDIファイルのパス。
            program: 使用する楽器のプログラム番号 (デフォルト: 1, ピアノ)。

        Returns:
            作成されたMIDIファイルのパス。
        """
        # (このメソッドの実装は変更なし)
        output_path = Path(output_path)
        if output_path.is_file():
            logger.warning(f"ファイルが既に存在するため上書きします: '{output_path}'")
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mid = mido.MidiFile()
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.Message("program_change", program=program, time=0))
        for note_info in notes:
            track.append(mido.Message("note_on", note=note_info["note"], velocity=note_info.get("velocity", 64), time=0))
            track.append(mido.Message("note_off", note=note_info["note"], velocity=note_info.get("velocity", 64), time=note_info["duration"]))
        mid.save(str(output_path))

        if not output_path.is_file():
             raise RuntimeError(f"MIDIファイルの作成に失敗しました: '{output_path}'")
        logger.success(f"MIDIファイルを作成しました: '{output_path}'")
        return output_path

    def midi_to_wav(
        self,
        midi_path: Union[str, Path],
        output_path: Union[str, Path],
        gain: float = 0.75,
        sampling_rate: int = 44100,
    ) -> Path:
        """FluidSynthを使い、MIDIファイルをWAVファイルに変換します。"""
        midi_path = Path(midi_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # --- 生成前の存在チェック ---
        if output_path.is_file():
            logger.warning(f"ファイルが既に存在するため上書きします: '{output_path}'")

        try:
            subprocess.run(
                [
                    "fluidsynth", "-ni",
                    "-g", str(gain), str(self.soundfont), str(midi_path),
                    "-F", str(output_path), "-r", str(sampling_rate),
                ],
                check=True, capture_output=True, text=True
            )
        except FileNotFoundError:
            raise RuntimeError("FluidSynthがインストールされていないか、パスが通っていません。")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FluidSynthの実行に失敗しました。\nError: {e.stderr}")

        # --- 生成後の実在チェック ---
        if not output_path.is_file():
            raise RuntimeError(f"WAVファイルの作成に失敗しました: '{output_path}'")

        logger.success(f"WAVファイルを作成しました: '{output_path}'")
        return output_path

    def wav_to_mp3(
        self,
        wav_path: Union[str, Path],
        output_path: Union[str, Path],
        volume_change_db: float = 0.0,
    ) -> Path:
        """WAVファイルをMP3ファイルに変換します。"""
        wav_path = Path(wav_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # --- 生成前の存在チェック ---
        if output_path.is_file():
            logger.warning(f"ファイルが既に存在するため上書きします: '{output_path}'")

        sound = AudioSegment.from_wav(wav_path)
        if volume_change_db != 0.0:
            sound += volume_change_db

        sound.export(str(output_path), format="mp3")

        # --- 生成後の実在チェック ---
        if not output_path.is_file():
            raise RuntimeError(f"MP3ファイルの作成に失敗しました: '{output_path}'")
        
        logger.success(f"MP3ファイルを作成しました: '{output_path}'")
        return output_path


if __name__ == "__main__":

    # --- 設定 ---
    SOUNDFONT_PATH = "data/raw/FluidR3_GM.sf2"
    OUTPUT_DIR = "data/interim"
    BASE_FILENAME = "sample_song"

    song_notes = [
        {"note": 60, "duration": 480},  # C4
        {"note": 62, "duration": 480},  # D4
        {"note": 64, "duration": 480},  # E4
        {"note": 65, "duration": 480},  # F4
        {"note": 67, "duration": 480},  # G4
    ]

    try:
        # --- 処理の実行 ---
        logger.info("オーディオ処理パイプラインを開始します...")
        audio_util = AudioUtility(soundfont_path=SOUNDFONT_PATH)

        midi_file = audio_util.create_midi_file(
            notes=song_notes,
            output_path=Path(OUTPUT_DIR) / f"{BASE_FILENAME}.mid"
        )

        wav_file = audio_util.midi_to_wav(
            midi_path=midi_file,
            output_path=Path(OUTPUT_DIR) / f"{BASE_FILENAME}.wav"
        )

        mp3_file = audio_util.wav_to_mp3(
            wav_path=wav_file,
            output_path=Path(OUTPUT_DIR) / f"{BASE_FILENAME}.mp3",
            volume_change_db=10.0
        )

        logger.success(f"処理が正常に完了しました: {mp3_file}")

    except (FileNotFoundError, RuntimeError) as e:
        logger.error(f"処理中にエラーが発生しました: {e}")

 
