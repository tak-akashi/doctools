# DocTools

ドキュメント変換・処理ツール集

## 概要

このリポジトリは、様々な形式のドキュメントを処理・変換するためのPythonスクリプト集です。主に以下の機能を提供します：

- WebページのスクレイピングとMarkdown変換
- PDFドキュメントのMarkdown変換
- Webコンテンツの抽出と整形
- Markdownドキュメントの分割処理

## スクリプト一覧

### 1. web_scraper_to_markdown.py

Webページをスクレイピングし、Markdown形式に変換するスクリプトです。

主な機能：
- Seleniumを使用したWebページのスクレイピング
- BeautifulSoup4によるHTML解析
- html2textによるMarkdown変換
- 複数URLの一括処理
- 特定サイト向けのカスタムセレクタ対応

### 2. pdf2markdown.py

PDFドキュメントをMarkdown形式に変換するスクリプトです。

主な機能：
- 2つの変換方式を提供
  - LLM（GPT-4）を使用した変換
  - Azure Document Intelligenceを使用した変換
- PDFのテキスト抽出と画像変換
- ページごとの処理と最終的な結合
- 表や画像の適切なMarkdown形式への変換

### 3. web_content_extractor.py

Webページから主要なコンテンツを抽出し、整形するスクリプトです。

主な機能：
- LLMを使用したメインコンテンツの識別
- HTMLの分割と処理
- 不要な要素（ナビゲーション、フッター等）の除去
- コンテンツの整理と結合

### 4. markdown_splitter.py

Markdownドキュメントを適切なサイズに分割するスクリプトです。

主な機能：
- LangChainを使用したMarkdownの分割
- ヘッダーレベルに基づく論理的な分割
- チャンクサイズの制御
- 分割時のコンテキスト保持

## 依存関係

主な依存パッケージ：
- selenium
- beautifulsoup4
- html2text
- pdfplumber
- pdf2image
- langchain
- openai
- azure-ai-documentintelligence

## 使用方法

各スクリプトの使用方法は、各ファイルのドキュメント文字列を参照してください。

## 注意事項

- 一部のスクリプトは環境変数の設定が必要です（APIキー等）
- Webスクレイピングを行う場合は、対象サイトの利用規約を確認してください
- PDF変換には十分なメモリとストレージ容量が必要です
