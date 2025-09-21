import os
from pathlib import Path
import tempfile

from midi2audio import FluidSynth
import mido
from src.model.melody_processor import MelodyControlLogitsProcessor
from src.model.utils import generate_midi_from_model, load_model_and_tokenizer
from tap import Tap
from tqdm import tqdm
import wandb
import weave


class MelodyEvaluator:
    """
    生成されたメロディを評価し、WandB Weaveに記録するためのクラス。
    """

    def __init__(self, model, tokenizer, note_tokenizer_helper, device):
        self.model = model
        self.tokenizer = tokenizer
        self.note_tokenizer_helper = note_tokenizer_helper
        self.device = device
        self.soundfont_path = None  # 自動検索に任せる

    def _parse_full_melody(self, midi_text: str) -> list[dict]:
        """生成されたMIDIテキストをノート情報の辞書のリストにパースする。"""
        notes = []
        lines = midi_text.strip().split("\n")
        # ヘッダー行をスキップ
        if lines and "pitch" in lines[0]:
            lines = lines[1:]

        for line in lines:
            parts = line.strip().split()
            if len(parts) == 5:
                try:
                    notes.append(
                        {
                            "pitch": int(parts[0]),
                            "duration": int(parts[1]),
                            "wait": int(parts[2]),
                            "velocity": int(parts[3]),
                            "instrument": int(parts[4]),
                        }
                    )
                except ValueError:
                    continue
        return notes

    def _calculate_metrics(self, parsed_notes: list[dict], allowed_pitches: set[int]) -> dict:
        """パースされたノート情報から定量的メトリクスを計算する。"""
        if not parsed_notes:
            return {
                "total_notes": 0,
                "unique_pitch_count": 0,
                "out_of_scale_ratio": 0.0,
                "average_interval": 0.0,
            }

        pitches = [note["pitch"] for note in parsed_notes]
        out_of_scale_count = sum(1 for p in pitches if p % 12 not in allowed_pitches)
        intervals = [abs(pitches[i] - pitches[i - 1]) for i in range(1, len(pitches))]
        average_interval = sum(intervals) / len(intervals) if intervals else 0.0

        return {
            "total_notes": len(pitches),
            "unique_pitch_count": len(set(pitches)),
            "out_of_scale_ratio": out_of_scale_count / len(pitches) if pitches else 0.0,
            "average_interval": average_interval,
        }

    def _create_wav_from_notes(self, parsed_notes: list[dict]) -> str | None:
        """ノート情報のリストからWAVファイルを生成し、一時ファイルのパスを返す。"""
        if not parsed_notes:
            return None
        mid = mido.MidiFile()
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120)))
        instrument = parsed_notes[0].get("instrument", 0)
        track.append(mido.Message("program_change", program=instrument, time=0))
        ticks_per_beat = mid.ticks_per_beat
        ms_per_tick = 500 / ticks_per_beat
        for note in parsed_notes:
            delay_ticks = int(note["wait"] / ms_per_tick)
            duration_ticks = int(note["duration"] / ms_per_tick)
            track.append(
                mido.Message(
                    "note_on", note=note["pitch"], velocity=note["velocity"], time=delay_ticks
                )
            )
            track.append(
                mido.Message(
                    "note_off", note=note["pitch"], velocity=note["velocity"], time=duration_ticks
                )
            )
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as mid_file:
            mid.save(mid_file.name)
            mid_path = mid_file.name
        wav_path = tempfile.mktemp(suffix=".wav")
        try:
            fs = FluidSynth(self.soundfont_path)
            fs.midi_to_audio(mid_path, wav_path)
            return wav_path
        except Exception as e:
            print(f"Error creating WAV file: {e}")
            return None
        finally:
            if os.path.exists(mid_path):
                os.remove(mid_path)

    @weave.op()
    def run_single_evaluation(self, chord_progression: str, style: str, variation: int) -> dict:
        """単一のテストケースで評価を実行し、結果を返す。"""
        all_notes_text = ""
        allowed_pitches_union = set()
        chords = [chord.strip() for chord in chord_progression.split("-")]
        for chord in chords:
            processor = MelodyControlLogitsProcessor(chord, self.note_tokenizer_helper)
            prompt = (
                f"style={style}, chord_progression={chord}\n"
                "pitch duration wait velocity instrument\n"
            )
            for token_id in processor.allowed_token_ids:
                decoded = self.tokenizer.decode([token_id])
                if decoded.strip().isdigit():
                    allowed_pitches_union.add(int(decoded.strip()) % 12)
            raw_output = generate_midi_from_model(
                self.model, self.tokenizer, self.device, prompt, processor, seed=variation
            )
            midi_text_part = raw_output.split("instrument\n")[-1]
            all_notes_text += midi_text_part.strip() + "\n"
        parsed_notes = self._parse_full_melody(all_notes_text)
        metrics = self._calculate_metrics(parsed_notes, allowed_pitches_union)
        wav_path = self._create_wav_from_notes(parsed_notes)
        results = {"output_text": all_notes_text.strip(), "scores": metrics}
        if wav_path:
            results["audio"] = wandb.Audio(wav_path, caption=f"{style} - var{variation}")
            os.remove(wav_path)
        return results


class Args(Tap):
    model_paths: list[str]
    wandb_project: str = "melody-flow-model-manage"
    evaluation_name: str = "default-evaluation"


def main():
    args = Args().parse_args()
    weave.init(args.wandb_project)
    base_evaluation_set = [
        {"chord_progression": "Dm7 - G7 - Cmaj7", "style": "JAZZ風"},
        {"chord_progression": "Am - G - C - F", "style": "POP風"},
    ]
    variations = [1, 42]
    full_evaluation_set = [
        {**case, "variation": var} for case in base_evaluation_set for var in variations
    ]
    for model_path in tqdm(args.model_paths, desc="Evaluating Models"):
        model_name_safe = Path(model_path).name
        print(f"\n--- Evaluating Model: {model_name_safe} ---")
        model, tokenizer, note_helper, device = load_model_and_tokenizer(model_path)
        if model is None:
            print(f"Skipping model {model_path} due to loading error.")
            continue
        evaluator = MelodyEvaluator(model, tokenizer, note_helper, device)
        _ = weave.Evaluation(
            dataset=full_evaluation_set,
            scorers=[evaluator.run_single_evaluation],
            name=f"{args.evaluation_name}-{model_name_safe}",
        )
    print("\n🎉 Evaluation finished! Check the results on the WandB dashboard.")


if __name__ == "__main__":
    main()
