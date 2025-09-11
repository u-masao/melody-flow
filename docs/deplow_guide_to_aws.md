# **Melody Flow デプロイガイド**

## **1\. 背景と目的**

### **背景**

Melody Flowは、ユーザーがブラウザで操作する「フロントエンド」と、AIがメロディを生成する「バックエンドAPI」の2つの主要コンポーネントで構成されています。これらはそれぞれ異なる技術的要件を持つため、個別のデプロイ戦略が必要です。

### **目的**

本ガイドは、Melody Flowアプリケーション全体をAWS (Amazon Web Services) 上にデプロイするための、一貫性のある手順を提供することを目的とします。目標は、以下の要件を満たす本番環境を構築することです。

* **高速なレスポンス:** CDNを利用してフロントエンドを高速に配信する。  
* **高いセキュリティ:** すべての通信をSSL/TLSで暗号化する。  
* **コスト効率:** GPUリソースを効率的に利用し、不要なコストを削減する。  
* **再現性と管理の容易さ:** Docker Composeを用いて、バックエンドの構成をコード化し、管理しやすくする。

## **2\. 構成概要**

このデプロイ構成は、静的サイト配信のベストプラクティスである「S3 \+ CloudFront」と、AIアプリケーションの実行に適した「EC2 \+ Docker」を組み合わせた、モダンでスケーラブルなアーキテクチャです。

### **全体構成図**

graph TD  
    subgraph "ユーザー"  
        U\[🌐 Browser\]  
    end

    subgraph "AWS Cloud"  
        subgraph "Frontend: melody-flow.click"  
            R53\_FE\[Route 53\] \--\> CF\[CloudFront w/ ACM SSL\] \--\> S3\[S3 Bucket\<br/\>(index.html, main.js)\]  
        end

        subgraph "Backend: api.melody-flow.click"  
            R53\_API\[Route 53\] \--\> EC2\[EC2 GPU Instance\]  
        end

        subgraph "EC2 Instance (Docker Compose)"  
            EC2 \--\> Nginx\[Nginx Container\<br/\>(Port 80/443)\]  
            Nginx \-- Port 8000 \--\> API\[API Container (FastAPI)\]  
            Certbot\[Certbot Container\] \-- Manages Certs for \--\> Nginx  
        end  
    end

    U \-- 1\. サイトアクセス \--\> R53\_FE  
    U \-- 2\. API呼び出し (JS) \--\> R53\_API

### **コンポーネント詳細**

| コンポーネント | 役割 |
| :---- | :---- |
| **Route 53** | melody-flow.click (フロントエンド) と api.melody-flow.click (バックエンド) の名前解決を担当するDNSサービス。 |
| **S3** | フロントエンドの静的ファイル (index.html, js, css等) を保管するストレージ。 |
| **ACM** | melody-flow.click 用の無料SSL証明書を発行・管理。 |
| **CloudFront** | S3のコンテンツを世界中にキャッシュ配信するCDN。ACMの証明書を使ってHTTPS化も担う。 |
| **EC2** | AIモデルを動かすためのGPU搭載仮想サーバー。コスト効率のためスポットインスタンスを利用。 |
| **Docker Compose** | EC2上で Nginx, API, Certbot の3つのコンテナを協調させて管理するツール。 |
| **Nginx (Container)** | APIへのリクエストを受け付けるリバースプロキシ。Let's Encryptの証明書でSSL終端を行う。 |
| **API (Container)** | FastAPIアプリケーションとAIモデルが動作する本体。 |
| **Certbot (Container)** | api.melody-flow.click 用の無料SSL証明書をLet's Encryptから取得・自動更新する。 |

## **3\. デプロイ手順**

### **3.1. 事前準備**

1. **AWSアカウント** を準備する。  
2. **Route 53** でドメイン melody-flow.click のホストゾーンを作成済みであること。  
3. ローカルマシンにプロジェクトのソースコード一式が準備できていること。

### **3.2. フロントエンドのデプロイ (S3 \+ CloudFront)**

1. **S3バケットの作成:**  
   * バケット名を melody-flow.click として作成。  
   * 「静的ウェブサイトホスティング」を有効化する。  
   * パブリックアクセスを許可するバケットポリシーを設定する。  
2. **ファイルのアップロード:**  
   * static/ ディレクトリ内の全ファイルをS3バケットにアップロードする。  
3. **SSL証明書のリクエスト (ACM):**  
   * **リージョンを「米国東部 (バージニア北部) us-east-1」に変更**する。  
   * AWS Certificate Manager (ACM) で melody-flow.click のパブリック証明書をリクエストし、DNS検証で発行する。  
4. **CloudFrontディストリビューションの作成:**  
   * オリジンに作成したS3バケットを指定する。  
   * **ビューワープロトコルポリシー:** Redirect HTTP to HTTPS を選択。  
   * **代替ドメイン名 (CNAMEs):** melody-flow.click を設定。  
   * **カスタムSSL証明書:** ステップ3で発行した証明書を選択。  
   * **デフォルトルートオブジェクト:** index.html を設定。  
5. **DNS設定 (Route 53):**  
   * melody-flow.click のホストゾーンで、melody-flow.click の **Aレコード** を作成する。  
   * エイリアスを有効にし、ターゲットとしてステップ4で作成したCloudFrontディストリビューションを選択する。

### **3.3. バックエンドのデプロイ (EC2 \+ Docker)**

1. **EC2インスタンスの起動:**  
   * **AMI:** Deep Learning Base OSS Nvidia Driver GPU AMI (Amazon Linux 2023\) などを選択。  
   * **インスタンスタイプ:** g4dn.xlarge などのGPUインスタンスを選択。  
   * **価格設定:** コスト削減のため「**スポットリクエスト**」を選択する。  
   * **セキュリティグループ:** SSH(22), HTTP(80), HTTPS(443) のインバウンド通信を許可する。  
2. **Elastic IPの割り当て:**  
   * Elastic IPアドレスを割り当て、起動したEC2インスタンスに関連付ける。  
3. **DNS設定 (Route 53):**  
   * melody-flow.click のホストゾーンで、api.melody-flow.click の **Aレコード** を作成する。  
   * 値として、ステップ2で設定したElastic IPアドレスを入力する。  
4. **サーバー環境構築:**  
   * SSHでEC2インスタンスに接続する。  
   * DockerとDocker Composeを手動でインストールする。  
   * Gitをインストールし、プロジェクトのリポジトリをクローンする。  
   * 学習済みモデル (models/) をEC2インスタンスにアップロードする。  
5. **SSL証明書の取得とサービス起動:**  
   * まず、nginx/nginx.confを**SSL設定前のシンプルなHTTP設定**にする。  
   * docker compose up \-d nginx api でNginxとAPIを起動する。  
   * docker compose run \--rm certbot certonly ... コマンドでSSL証明書を取得する。  
   * 証明書が取得できたら、nginx/nginx.confを**SSL設定後の最終版**に書き換える。  
   * docker compose restart nginx でNginxを再起動し、SSL設定を反映させる。

### **3.4. 動作確認**

1. ブラウザで https://melody-flow.click にアクセスし、フロントエンドが正しく表示されることを確認する。  
2. ブラウザで https://api.melody-flow.click/docs にアクセスし、FastAPIのドキュメントが表示されることを確認する。  
3. フロントエンドのアプリケーションを操作し、AIとのセッションが正常に動作することを確認する。
