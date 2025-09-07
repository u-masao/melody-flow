# アーキテクチャ

Melody Flow のアーキテクチャ



## 1. AIモデルの系統とファインチューニングのプロセス

dx2102/llama-midiがどのように作られ、このプロジェクトでさらにどう進化したかを図示します。


```mermaid
---
title: Melody Flow AIモデルの学習プロセス
---
graph TD
    subgraph "Hugging Face上の公開アセット"
        Base("Base Model<br/>eta-llama/Llama-3.2-8B-Instruct")
        DS1[("amaai-lab/MidiCaps")]
        DS2[("projectlosangeles/Los-Angeles-MIDI-Dataset")]
    end

    subgraph "dx2102/llama-midi (事前学習)"
        FT1("Fine-Tuning")
        LlamaMidi("dx2102/llama-midi")
    end

    subgraph "Melody Flow プロジェクト"
        WJazzD[("Weimar Jazz Database")]
        ProjFT("<b>Fine-Tuning (本プロジェクト)</b><br/>Unslothによる高速化<br/>LoRAによる効率的学習")
        FinalModel("🏆 Melody Flow 専用モデル")
    end

    Base --> FT1
    DS1 --> FT1
    DS2 --> FT1
    FT1 --> LlamaMidi

    LlamaMidi --> ProjFT
    WJazzD --> ProjFT
    ProjFT --> FinalModel
```



## 2. システム全体のアーキテクチャ (シーケンス図)

ユーザーのMIDI入力が、どのようにブラウザとバックエンドの間で処理されるかを図示します。演奏中のリアルタイム性を担保するために、AIによるフレーズ生成を事前に行う点がアーキテクチャの重要なポイントです。


```mermaid
---
title: Melody Flow システムアーキテクチャ
---
sequenceDiagram
    actor User
    participant Browser (JavaScript)
    participant Backend (Python/FastAPI)

    Note over User, Backend (Python/FastAPI): 【フェーズ1】フレーズの事前生成 (演奏開始前)

    User->>Browser (JavaScript): 1. コード進行を選択し「フレーズをAIに生成させる」
    activate Browser (JavaScript)
    Browser (JavaScript)->>Backend (Python/FastAPI): 2. POST /generate (コード進行)
    activate Backend (Python/FastAPI)
    Backend (Python/FastAPI)->>Backend (Python/FastAPI): 3. LLMがフレーズ群を予測生成<br/>(MelodyControlLogitsProcessorが介在)
    Backend (Python/FastAPI)-->>Browser (JavaScript): 4. Base64エンコードされたフレーズ群を返却
    deactivate Backend (Python/FastAPI)
    Browser (JavaScript)->>Browser (JavaScript): 5. フレーズ群をデコードしてJS変数に保持
    deactivate Browser (JavaScript)

    Note over User, Browser (JavaScript): 【フェーズ2】リアルタイム演奏 (BackendへのAPI通信なし)

    User->>Browser (JavaScript): 6. MIDI IN / キーボード入力 (Note On)
    activate Browser (JavaScript)
    Browser (JavaScript)->>Browser (JavaScript): 7. 保持しているフレーズから次のNoteを選択
    Browser (JavaScript)->>User: 8. Tone.jsで選択されたNoteを発音
    deactivate Browser (JavaScript)

    User->>Browser (JavaScript): 9. MIDI IN / キーボード入力 (Note Off)
    activate Browser (JavaScript)
    Browser (JavaScript)->>Browser (JavaScript): 10. 発音を停止
    deactivate Browser (JavaScript)
```

## 3. MelodyControlLogitsProcessor の内部処理フロー

バックエンドでAIが次の音を予測する瞬間に、どのように音楽理論に基づいた制約をかけているかを図示します。


```mermaid
---
title: MelodyControlLogitsProcessor の処理フロー
---
flowchart TD
    A(Start: LLMが次のTokenを予測) --> B{生成中のシーケンス末尾が改行か？}

    B -- No --> K(処理をスキップし、LLMの予測をそのまま利用)

    B -- Yes (次のNoteを予測するタイミング) --> C(現在のコードと過去のNote履歴を取得)

    subgraph "音楽理論に基づく制約ルール"
        C --> D["chord_name_parser.py<br/>コード名を解析し、使用可能なスケール音を特定"]
        C --> E["calc_trend<br/>直近数音の平均ピッチ(トレンド)を計算"]
    end

    subgraph "Logits (確率分布) の操作"
        D --> F(スケール音とトレンドから<br/><b>許容するNote</b>のToken IDリストを作成)
        E --> F
        F --> G(許容リストに<b>含まれない</b>Note Tokenの<br/>Logitsに強いペナルティを課す)
    end

    G --> H(補正されたLogitsから<br/>次のNote Tokenをサンプリング)
```
