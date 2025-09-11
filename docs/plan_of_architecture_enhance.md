# **LLM APIサーバー 構想・要件定義書**

## **1\. 概要**

本ドキュメントは、特定のクエリセットに対するLLM（大規模言語モデル）の応答を、低コストかつ高パフォーマンスで提供するAPIサーバーの構想と要件を定義するものである。

利用頻度が低く、提供するクエリが限定的であるという特性を活かし、段階的なアプローチで迅速な価値提供と将来の拡張性を両立させる。

## **2\. 全体構想：段階的リリース計画**

本プロジェクトは、以下の2フェーズで開発を進める。

* **フェーズ1: キャッシュ導入による迅速なサービスイン**  
  * **目的**: 既存のNginx環境を最小限の変更で活用し、GPUを一切稼働させずにサービスを即時リリースする。  
  * **提供価値**: 超高速・高安定な応答。  
* **フェーズ2: 完全サーバーレス化によるコスト最適化と拡張性確保**  
  * **目的**: アイドルコストを完全にゼロにし、将来的な機能拡張（動的なクエリ応答など）に対応可能なアーキテクチャへ移行する。  
  * **提供価値**: 究極のコスト効率とスケーラビリティ。

## **3\. フェーズ1: キャッシュ導入による迅速なサービスイン**

### **3.1. 目的**

* GPUインスタンスを稼働させることなく、定義済みの10パターンのクエリに対して、それぞれ5つのバリエーションを持つ応答をランダムに返すAPIを構築する。  
* 既存のNginx環境を活用し、数時間以内の実装を目指す。  
* 応答速度はミリ秒単位とし、安定したユーザー体験を提供する。

### **3.2. アーキテクチャ**

既存のNginxリバースプロキシにディスクキャッシュ機能を追加する。バックエンドのLLMサーバーは、キャッシュを生成するためのデータソースとして**一度だけ**利用する。

### **3.3. 主要コンポーネントと要件**

#### **1\. 事前生成データ**

* **要件**:  
  * 定義済みの10パターンのクエリそれぞれに対し、5つの異なる応答を事前にLLMで生成しておく。  
  * 合計50個の応答データをテキストファイル等で管理する。

#### **2\. Nginx設定 (nginx.conf)**

* **要件**:  
  * proxy\_cache\_path ディレクティブを使用し、キャッシュの保存先パス、キー管理用の共有メモリゾーン、最大サイズ等を定義する。  
  * location ブロックにて proxy\_cache を有効化する。  
  * キャッシュキーには、プロンプトとランダムな接尾辞（例: \#1）の組み合わせを想定した設計とする。  
    * *注: Nginx単体でのランダムなキー振り分けは複雑なため、後述のwarmup.shで5パターンのリクエストを投げることでキャッシュを生成する。*

#### **3\. キャッシュデータの永続化 (Docker Volume)**

* **要件**:  
  * Nginxコンテナを再作成してもキャッシュが消えないよう、Dockerの名前付きボリュームを使用する。  
  * docker-compose.ymlにてボリュームを定義し、Nginxコンテナ内のキャッシュディレクトリ (proxy\_cache\_pathで指定したパス) にマウントする。

#### **4\. 運用自動化 (Makefile & Shell Script)**

* **要件**:  
  * キャッシュの生成（ウォームアップ）、エクスポート、別マシンへのコピー、インポートといった一連の運用タスクを自動化するMakefileを導入する。  
  * キャッシュウォームアップには、10クエリ×5回のPOSTリクエストを送信するcurlを用いたシェルスクリプト (warmup.sh) を使用する。

### **3.4. 期待される成果**

* GPUのランニングコストなしで、定義済みクエリに対するLLM応答APIをサービスインできる。  
* すべての応答がキャッシュから返されるため、高速かつ安定したパフォーマンスが保証される。  
* Makefileにより、キャッシュの管理・デプロイ作業が標準化され、属人性が排除される。

## **4\. フェーズ2: 完全サーバーレス化**

### **4.1. 目的**

* フェーズ1のサービスを、アイドルコストが完全にゼロのサーバーレスアーキテクチャに移行する。  
* 将来的に未知のクエリに対して動的に応答を生成（GPUインスタンスをオンデマンドで起動）する機能拡張の礎を築く。

### **4.2. アーキテクチャ**

APIの全リクエストをAPI GatewayとLambdaで受け、応答データはDynamoDBで管理する。

### **4.3. 主要コンポーネントと要件**

#### **1\. データストア (Amazon DynamoDB)**

* **要件**:  
  * フェーズ1で事前生成した50個の応答データをDynamoDBに格納する。  
  * テーブル設計は、元のプロンプトをパーティションキー、応答のバリエーション番号（0〜4）をソートキーとする構成を推奨。

#### **2\. APIエンドポイント (Amazon API Gateway)**

* **要件**:  
  * HTTPリクエストを受け付け、バックエンドのLambda関数をトリガーするエンドポイントを作成する。

#### **3\. ビジネスロジック (AWS Lambda)**

* **要件**:  
  * API Gatewayからリクエストボディ（プロンプト）を受け取る。  
  * 0〜4のランダムな整数を生成する。  
  * プロンプトとランダムな整数をキーとして、DynamoDBから対応する応答データを取得する。  
  * 取得した応答データをクライアントに返す。

### **4.4. 期待される成果**

* APIへのリクエストがない限り、一切のコンピューティングコストが発生しないゼロアイドルコスト運用が実現する。  
* AWSのマネージドサービスで構成されるため、サーバーの管理・運用負荷が大幅に軽減される。  
* Lambda関数にロジックを追加することで、「未知のクエリが来たらEC2のGPUインスタンスを起動する」といった動的な機能拡張を容易に行えるようになる。

## **補足資料: フェーズ1運用自動化のためのMakefileサンプル**

\# \==============================================================================  
\# Makefile for LLM API Cache Management  
\# \==============================================================================

\# \--- Variables \---  
COMPOSE\_PROJECT\_NAME := $(shell basename $(CURDIR))  
CACHE\_VOLUME\_NAME := $(COMPOSE\_PROJECT\_NAME)\_nginx\_cache\_data  
EXPORT\_FILE := nginx\_cache.tar.gz  
REMOTE\_HOST := user@remote.server.com  
REMOTE\_PATH := /tmp/nginx\_cache\_import/

\# \--- Targets \---  
.PHONY: warmup cache-export cache-copy cache-import all

all: warmup cache-export cache-copy cache-import  
    @echo "✅ All cache management tasks completed."

warmup:  
    @echo "🚀 Warming up Nginx cache..."  
    @./warmup.sh  
    @echo "✅ Cache warmup complete."

cache-export:  
    @echo "📦 Exporting cache data from volume \[$(CACHE\_VOLUME\_NAME)\] to \[$(EXPORT\_FILE)\]..."  
    @docker run \--rm \\  
        \-v $(CACHE\_VOLUME\_NAME):/cache\_data \\  
        \-v $(CURDIR):/backup \\  
        alpine tar czf /backup/$(EXPORT\_FILE) \-C /cache\_data .  
    @echo "✅ Cache data exported successfully."

cache-copy:  
    @echo "🚚 Copying \[$(EXPORT\_FILE)\] to \[$(REMOTE\_HOST)\]..."  
    @scp $(EXPORT\_FILE) $(REMOTE\_HOST):/tmp/  
    @echo "✅ File copied successfully."

cache-import:  
    @echo "📥 Importing cache data on remote machine..."  
    @ssh $(REMOTE\_HOST) ' \\  
        mkdir \-p $(REMOTE\_PATH) && \\  
        tar xzf /tmp/$(EXPORT\_FILE) \-C $(REMOTE\_PATH) && \\  
        docker volume create $(CACHE\_VOLUME\_NAME) && \\  
        docker run \--rm \\  
            \-v $(CACHE\_VOLUME\_NAME):/new\_cache \\  
            \-v $(REMOTE\_PATH):/backup \\  
            alpine sh \-c "cp \-a /backup/. /new\_cache/" && \\  
        rm \-rf /tmp/$(EXPORT\_FILE) $(REMOTE\_PATH) && \\  
        echo "✅ Remote cache import complete." \\  
    '  
