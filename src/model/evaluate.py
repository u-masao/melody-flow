import unsloth  # noqa: F401
import os
import re
import textwrap
from pathlib import Path
import tempfile
from typing import Any

from loguru import logger
from src.model.audio import AudioUtility
from src.model.melody_processor import MelodyControlLogitsProcessor
from src.model.utils import generate_midi_from_model, load_model_and_tokenizer
from src.model.visualize import create_pianoroll_image
from tap import Tap
from tqdm import tqdm
import wandb
import weave


class MelodyGenerator:
    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        note_tokenizer_helper: Any,
        device: Any,
        soundfont_path: str,
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.note_tokenizer_helper = note_tokenizer_helper
        self.device = device
        self.audio_util = AudioUtility(soundfont_path=soundfont_path)

    def _parse_and_pickup_notes(self, decoded_text: str, head_k: int = 5) -> str:
        """main.pyから移植: 生成されたテキストからノート部分だけを抽出し、次のプロンプトに渡す"""
        match = re.search(
            r"pitch duration wait velocity instrument\s*\n(.*)", decoded_text, re.DOTALL
        )
        midi_note_data = match.group(1).strip() if match else decoded_text
        # EOSトークンなどが含まれる場合があるので、有効な行のみを抽出
        notes = [
            line.split(" ")[0]
            for line in midi_note_data.split("\n")
            if line.strip() and " " in line
        ]
        return " ".join(notes[:head_k])

    def _parse_full_melody(self, midi_text: str) -> list[dict[str, int]]:
        notes = []
        lines = midi_text.strip().split("\n")
        # ヘッダー行があればスキップ
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
                except (ValueError, IndexError):
                    continue
        return notes

    def _calculate_metrics(
        self, parsed_notes: list[dict[str, int]], allowed_pitches: set[int]
    ) -> dict[str, float]:
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

    def _create_wav_from_notes(self, parsed_notes: list[dict[str, int]]) -> bytes | None:
        if not parsed_notes:
            return None

        utility_notes = [
            {"note": n["pitch"], "duration": n["duration"], "velocity": n["velocity"]}
            for n in parsed_notes
        ]

        temp_dir = tempfile.mkdtemp()
        mid_path = Path(temp_dir) / "temp.mid"
        wav_path = Path(temp_dir) / "temp.wav"

        try:
            self.audio_util.create_midi_file(notes=utility_notes, output_path=mid_path)
            self.audio_util.midi_to_wav(midi_path=mid_path, output_path=wav_path, gain=0.9)

            with open(wav_path, "rb") as f:
                wav_data = f.read()
                return wav_data

        except Exception as e:
            logger.error(f"Error creating WAV file: {e}")
            return None
        finally:
            for f in os.listdir(temp_dir):
                os.remove(os.path.join(temp_dir, f))
            os.rmdir(temp_dir)

    def run_single_prediction(
        self,
        chord_progression: str,
        style: str,
        variation: int,
        supress_token_prob_ratio: float = 0.3,
        instrument: str = "Alto Saxophone",  # main.pyから移植
    ) -> dict[str, Any]:
        logger.info(f"Running prediction for: {style} - {chord_progression} - var{variation}")
        all_notes_text = ""
        allowed_pitches_union = set()
        chords = [chord.strip() for chord in chord_progression.split("-")]

        # ▼▼▼ 【変更点】main.pyのロジックを移植 ▼▼▼
        prev_bar_notes = ""

        for bars, chord in enumerate(chords):
            processor = MelodyControlLogitsProcessor(
                chord,
                self.note_tokenizer_helper,
                supress_token_prob_ratio=supress_token_prob_ratio,
            )
            # main.pyからプロンプトを移植
            prompt = f"""
                Act as a world-class jazz musician improvising over a chord progression.
                Your task is to generate a single bar of a masterful melodic phrase for
                the specific chord at the current position in the progression.
                - Style: {style}
                - Full Chord Progression: {chord_progression}
                - Current Bar Number: {bars + 1}
                - Chord for This Bar: {chord}
                - Prev Bar Notes: {prev_bar_notes}
                - Instrument: {instrument}
                Generate the melody for this bar only. The output format is:
                pitch duration wait velocity instrument
                """
            prompt = textwrap.dedent(prompt).strip()
            # ▲▲▲ 【ここまで】 ▲▲▲

            for token_id in processor.allowed_token_ids:
                decoded = self.tokenizer.decode([token_id])
                if decoded.strip().isdigit():
                    allowed_pitches_union.add(int(decoded.strip()) % 12)

            raw_output = generate_midi_from_model(
                self.model, self.tokenizer, self.device, prompt, processor, seed=variation
            )

            # ▼▼▼ 【変更点】main.pyのロジックを移植 ▼▼▼
            # ヘッダー以降のMIDIテキスト部分を抽出
            midi_text_part = re.search(r"instrument\s*\n(.*)", raw_output, re.DOTALL)
            if midi_text_part:
                clean_midi_text = midi_text_part.group(1).strip()
                all_notes_text += clean_midi_text + "\n"
                # 次の小節のために、生成されたノートをパース
                prev_bar_notes = self._parse_and_pickup_notes(raw_output)
            else:
                # もしヘッダーが見つからなければ、元のテキストをそのまま使う
                all_notes_text += raw_output.replace(prompt, "").strip() + "\n"
                prev_bar_notes = self._parse_and_pickup_notes(raw_output)
            # ▲▲▲ 【ここまで】 ▲▲▲

        parsed_notes = self._parse_full_melody(all_notes_text)
        metrics = self._calculate_metrics(parsed_notes, allowed_pitches_union)
        wav_data = self._create_wav_from_notes(parsed_notes)
        pianoroll_image = create_pianoroll_image(parsed_notes)

        results = {"output_text": all_notes_text.strip(), "scores": metrics}
        if wav_data:
            results["audio"] = weave.Audio(wav_data, format="wav")
        if pianoroll_image:
            results["pianoroll"] = pianoroll_image

        return results


class Args(Tap):
    model_paths: list[str]
    wandb_project: str = "melody-flow-model-manage"
    evaluation_name: str = "default-evaluation"
    soundfont_path: str = "data/raw/FluidR3_GM.sf2"


def main():
    args = Args().parse_args()
    weave.init(args.wandb_project)
    base_evaluation_set = [
        {
            "chord_progression": "Dm7 - G7 - Cmaj7",
            "style": "JAZZ風",
            "supress_token_prob_ratio": 0.3,
        },
        {
            "chord_progression": "Am - G - C - F",
            "style": "POP風",
            "supress_token_prob_ratio": 0.3,
        },
    ]
    variations = [1, 42]
    full_evaluation_set = [
        {**case, "variation": var} for case in base_evaluation_set for var in variations
    ]

    for model_path in tqdm(args.model_paths, desc="Evaluating Models"):
        model_name_safe = Path(model_path).name
        logger.info(f"--- Evaluating Model: {model_name_safe} ---")

        model, tokenizer, note_helper, device = load_model_and_tokenizer(
            model_path, disable_unsloth=False
        )

        if model is None:
            logger.info(f"Skipping model {model_path} due to loading error.")
            continue

        melody_generator = MelodyGenerator(
            model=model,
            tokenizer=tokenizer,
            note_tokenizer_helper=note_helper,
            device=device,
            soundfont_path=args.soundfont_path,
        )

        evaluation_name = f"{args.evaluation_name}-{model_name_safe}"
        eval_logger = weave.EvaluationLogger(name=evaluation_name)

        for example in tqdm(full_evaluation_set, desc=f"Running {evaluation_name}"):
            output = melody_generator.run_single_prediction(**example)

            pred_logger = eval_logger.log_prediction(inputs=example, output=output)

            if "scores" in output:
                for score_name, score_value in output["scores"].items():
                    pred_logger.log_score(scorer=score_name, score=score_value)

            pred_logger.finish()

        eval_logger.log_summary()

    logger.info("🎉 All evaluations finished! Check the results on the WandB dashboard.")
    wandb.finish()


if __name__ == "__main__":
    main()
