import base64
import re
import time
import os

from loguru import logger
from src.model.melody_processor import MelodyControlLogitsProcessor, NoteTokenizer
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, LogitsProcessorList
from unsloth import FastLanguageModel

from . import config


class ModelManager:
    """
    機械学習モデルとトークナイザーのロードと可用性を管理します。
    """

    def __init__(self, model_name: str, device: str):
        self.model_name = model_name
        self.device = device
        self.model = None
        self.tokenizer = None
        self.note_tokenizer = None
        self._load()

    def _load(self):
        """指定されたパスからモデルとトークナイザーをロードします。"""
        logger.info(f"モデルをロード中: {self.model_name}...")
        logger.info(f"使用デバイス: {self.device}")
        try:
            if os.path.isdir(self.model_name):
                logger.info("ローカルのUnslothモデルをロード中...")
                self.model, self.tokenizer = FastLanguageModel.from_pretrained(
                    model_name=self.model_name,
                    max_seq_length=4096,
                    dtype=None,
                    load_in_4bit=True,
                )
            else:
                logger.info("HuggingFaceモデルをロード中...")
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_name,
                    torch_dtype=torch.bfloat16,
                ).to(self.device)
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)

            self.note_tokenizer = NoteTokenizer(self.tokenizer)
            logger.success("モデルのロードが成功しました。")
        except Exception as e:
            logger.error(f"モデルのロード中にエラーが発生しました: {e}")
            # 失敗したことを示すためにNoneを維持します
            self.model, self.tokenizer, self.note_tokenizer = None, None, None

    def is_ready(self) -> bool:
        """モデルとトークナイザーがロードされているか確認します。"""
        return self.model is not None and self.tokenizer is not None


class MelodyGenerationService:
    """
    コード進行に基づいたメロディ生成サービスを提供します。
    """

    def __init__(self, model_manager: ModelManager):
        self.model_manager = model_manager

    def _generate_midi_from_model(self, prompt: str, processor: MelodyControlLogitsProcessor) -> str:
        """プロンプトとプロセッサを元に、モデルから生のMIDIテキストを生成します。"""
        if not self.model_manager.is_ready():
            raise RuntimeError("モデルがロードされていません。")

        inputs = self.model_manager.tokenizer(prompt, return_tensors="pt").to(config.DEVICE)
        logits_processors = LogitsProcessorList([processor])

        output = self.model_manager.model.generate(
            **inputs,
            max_new_tokens=config.DEFAULT_MAX_NEW_TOKENS,
            temperature=config.DEFAULT_TEMPERATURE,
            pad_token_id=self.model_manager.tokenizer.eos_token_id,
            logits_processor=logits_processors,
        )
        return self.model_manager.tokenizer.decode(output[0])

    def _parse_and_encode_midi(self, decoded_text: str) -> str:
        """モデルの生出力をパースし、MIDIノートデータをBase64エンコードします。"""
        match = re.search(r"pitch duration wait velocity instrument\s*\n(.*)", decoded_text, re.DOTALL)
        midi_note_data = match.group(1).strip() if match else decoded_text
        return base64.b64encode(midi_note_data.encode("utf-8")).decode("utf-8")

    def generate_melodies_for_chords(self, chord_progression: str, style: str) -> tuple[dict, dict]:
        """
        進行内の各コードに対してメロディを生成します。
        (エンコードされたメロディ, 生の出力) のタプルを返します。
        """
        total_start_time = time.time()
        chords = [chord.strip() for chord in chord_progression.split("-")]

        melodies = {}
        raw_outputs = {}

        logger.info(f"コードのメロディを生成中: {chords}")
        for chord in chords:
            chord_start_time = time.time()

            processor = MelodyControlLogitsProcessor(chord, self.model_manager.note_tokenizer)
            prompt = (
                f"style={style}, chord_progression={chord}\n"
                "pitch duration wait velocity instrument\n"
            )

            raw_output = self._generate_midi_from_model(prompt, processor)
            encoded_midi = self._parse_and_encode_midi(raw_output)

            # 重複したコード名を処理します
            key = chord
            count = 2
            while key in melodies:
                key = f"{chord}_{count}"
                count += 1

            melodies[key] = encoded_midi
            raw_outputs[key] = raw_output

            chord_end_time = time.time()
            logger.info(f"  - {key} の生成完了 ({chord_end_time - chord_start_time:.2f}秒)")

        total_end_time = time.time()
        logger.info(f"総生成時間: {total_end_time - total_start_time:.2f}秒")

        return melodies, raw_outputs
