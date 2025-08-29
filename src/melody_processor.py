import torch
from transformers import LogitsProcessor

class MelodyControlLogitsProcessor(LogitsProcessor):
    """
    メロディの音楽的品質を制御するためのLogitsProcessor。
    生成される次のトークン（音）の確率分布をリアルタイムで操作する。
    """
    def __init__(self, chord: str, style: str, note_tokenizer):
        """
        Args:
            chord (str): 現在のコード（例: "Cmaj7"）
            style (str): 音楽スタイル（例: "JAZZ"）
            note_tokenizer: MIDIトークンと音名を相互変換するためのトケナイザ
        """
        self.chord = chord
        self.style = style
        self.tokenizer = note_tokenizer
        
        # コード理論に基づき、許可する音のリストを初期化
        self.allowed_note_indices = self._get_allowed_note_indices_for_chord(chord)
        print(f"Processor initialized for chord: {self.chord}. Allowed note indices: {self.allowed_note_indices}")

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor) -> torch.FloatTensor:
        """
        Args:
            input_ids (torch.LongTensor): これまでに生成されたトークンのシーケンス
            scores (torch.FloatTensor): 次のトークンの確率分布（logits）
        
        Returns:
            torch.FloatTensor: 加工後の確率分布
        """
        # --- ハーモニー制約ルール ---
        # 許可されていない音の確率を-infに設定する
        
        # 作成した許可リストを使って、許可されていない音の確率を操作する
        # 全ての可能なトークンIDをループ
        for token_id in range(scores.shape[1]):
            # トークンIDをデコードして、それが音符（NOTE_ON）かチェック
            token_str = self.tokenizer.decode([token_id])
            try:
                if "NOTE_ON" in token_str:
                    pitch = int(token_str.split('_')[-1])
                    note_index = pitch % 12 # C=0, C#=1, ... B=11
                    
                    # 許可リストに含まれていない音の場合
                    if note_index not in self.allowed_note_indices:
                        scores[:, token_id] = -float('Inf') # 確率を-無限大にして選択させない
                
                # NOTE_OFFや他のトークンはそのまま
            except (ValueError, IndexError):
                # NOTE_ON形式でないトークンは無視
                continue

        return scores

    def _get_allowed_note_indices_for_chord(self, chord: str) -> list[int]:
        """
        コード名から、使用を許可するMIDIピッチのノートナンバー（0-11）のリストを返す。
        
        Args:
            chord (str): コード名
        
        Returns:
            list[int]: C=0, C#=1...B=11としたノートナンバーのリスト
        """
        # 非常にシンプルな音楽理論に基づくマッピング
        # ここを拡張することで、より複雑なスケール（例：オルタードスケール）にも対応可能
        chord = chord.lower()
        if "c" in chord:
            # Cメジャースケール
            return [0, 2, 4, 5, 7, 9, 11]
        elif "g" in chord:
            # Gメジャースケール
            return [0, 2, 4, 5, 7, 9, 10]
        elif "am" in chord:
             # Aマイナースケール
            return [0, 2, 3, 5, 7, 8, 10]
        elif "f" in chord:
            # Fメジャースケール
            return [0, 1, 3, 5, 6, 8, 10]
        else:
            # デフォルトはCメジャースケール
            return [0, 2, 4, 5, 7, 9, 11]

