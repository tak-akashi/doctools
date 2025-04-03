import argparse
import os
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import re
import time
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_text_splitters import HTMLHeaderTextSplitter, RecursiveCharacterTextSplitter
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

class WebContentExtractor:
    def __init__(self, api_key=None, model="gpt-4o"):
        # APIキーが指定されていなければ環境変数から取得
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI APIキーが必要です。OPENAI_API_KEYとして環境変数に設定するか、引数で指定してください。")
        
        # LLMモデルの初期化
        self.model = model
        self.llm = ChatOpenAI(
            api_key=self.api_key, 
            model=self.model, 
            temperature=0,
            request_timeout=120,  # タイムアウトを120秒に設定
            max_retries=3  # リトライ回数を設定
        )
        
        # GPT-4oの出力トークン制限（約4000トークン）
        self.output_token_limit = 2000  # より安全なマージンを取って2000に設定
        
        # 分割用の処理
        # HTMLヘッダーのレベルでコンテンツを分割するための設定
        self.html_splitter = HTMLHeaderTextSplitter(
            headers_to_split_on=[
                ("h1", "header_1"),
                ("h2", "header_2"),
                ("h3", "header_3"),
                ("h4", "header_4"),
            ]
        )
        
        # 通常のテキスト分割用のスプリッター (チャンクサイズを小さく設定)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,  # より小さなチャンクサイズ
            chunk_overlap=100,
        )
        
        # プロンプトテンプレートの作成
        self.identification_prompt = PromptTemplate.from_template(
            """あなたはHTMLからメインコンテンツを識別する専門家です。
            以下のHTMLについて、ナビゲーションバー（トップ）、ナビゲーションパネル（左右）、
            ページ下部のアンケートやリンクなどを除外し、ページの主要な内容がどの部分に含まれているか識別してください。
            
            可能であれば、メインコンテンツを含む要素のセレクタ（id、classなど）を特定してください。
            複数の要素に分かれている場合は、それぞれのセレクタを示してください。
            
            HTMLの一部:
            {html_content}
            
            出力形式:
            メインコンテンツセレクタ: [セレクタのリスト、例: '#main-content', '.article-body' など]
            """
        )
        
        self.extraction_prompt = PromptTemplate.from_template(
            """あなたはHTMLからメインコンテンツを抽出する専門家です。
            以下のHTMLの断片から、ページの主要な内容だけを抽出してください。
            
            抽出するときは、HTMLタグを保持してください。ただし、不要なdivやspanなどは削除し、
            メインコンテンツに関連するタグのみを保持してください。
            
            これは長いHTMLの一部（{part_num}/{total_parts}）です。前後のコンテキストとの一貫性を保ちながら抽出してください。
            
            HTMLコンテンツ:
            {html_content}
            
            メインコンテンツのHTMLだけを出力してください。余計な説明は不要です。
            """
        )
        
        self.consolidation_prompt = PromptTemplate.from_template(
            """あなたはHTMLを整理する専門家です。
            以下の複数のHTMLフラグメントを適切に結合して、一貫性のある完全なHTMLを作成してください。
            重複している部分があれば削除し、すべてのコンテンツが論理的に繋がるようにしてください。
            
            HTMLフラグメント:
            {html_fragments}
            
            結合されたHTMLを出力してください。余計な説明は不要です。
            """
        )
    
    def _clean_html(self, html_content):
        """HTMLの基本的なクリーニングを行う"""
        # コメント、スクリプト、スタイルタグを削除
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # コメントを削除 (非推奨警告を回避するためにstringを使用)
        for comment in soup.find_all(string=lambda text: isinstance(text, str) and '<!--' in text):
            comment.extract()
        
        # スクリプトとスタイルタグを削除
        for tag in soup(['script', 'style', 'noscript', 'iframe', 'svg']):
            tag.decompose()
        
        # 不要と思われる要素を削除
        for tag in soup(['nav', 'header', 'footer']):
            tag.decompose()
            
        # 空白行を削除
        cleaned_html = re.sub(r'\n\s*\n', '\n', str(soup))
        return cleaned_html
    
    def _identify_main_content_selectors(self, html_content):
        """LLMを使用してメインコンテンツのセレクタを識別する"""
        prompt = self.identification_prompt.format(html_content=html_content[:15000])
        result = self.llm.invoke(prompt)
        
        # セレクタを抽出
        selectors = []
        if 'メインコンテンツセレクタ:' in result.content:
            selectors_text = result.content.split('メインコンテンツセレクタ:')[1].strip()
            # リスト形式 ['.class', '#id'] から抽出
            if '[' in selectors_text and ']' in selectors_text:
                selectors_text = selectors_text.split('[')[1].split(']')[0]
                selectors = [s.strip().strip("'").strip('"') for s in selectors_text.split(',')]
            else:
                # 単一のセレクタまたは別の形式の場合
                selectors = [selectors_text.strip()]
        
        return selectors
    
    def _extract_by_selectors(self, html_content, selectors):
        """指定されたセレクタを使用してHTMLからメインコンテンツを抽出する"""
        soup = BeautifulSoup(html_content, 'html.parser')
        main_elements = []
        
        for selector in selectors:
            selector = selector.strip()
            if not selector:
                continue
                
            # IDセレクタ
            if selector.startswith('#'):
                element = soup.select_one(selector)
                if element:
                    main_elements.append(element)
            # クラスセレクタ
            elif selector.startswith('.'):
                elements = soup.select(selector)
                main_elements.extend(elements)
            # タグセレクタ
            else:
                # 特定のタグ名が指定されている場合
                elements = soup.find_all(selector)
                main_elements.extend(elements)
        
        # 重複を削除
        unique_elements = []
        for element in main_elements:
            if element not in unique_elements:
                unique_elements.append(element)
        
        # 見つかった要素をHTMLとして結合
        if unique_elements:
            return ''.join(str(element) for element in unique_elements)
        
        return None
    
    def _split_html_into_chunks(self, html_content, max_chunk_size=3000):
        """HTMLを処理可能なチャンクに分割する（より小さなチャンクサイズを使用）"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 主要なブロック要素を取得
        block_elements = soup.find_all(['div', 'section', 'article', 'main', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        
        chunks = []
        current_chunk = ""
        
        for element in block_elements:
            element_html = str(element)
            
            # 要素が単体で最大サイズを超える場合は、その要素自体を更に分割
            if len(element_html) > max_chunk_size:
                # 大きな要素を内部の段落や見出しで分割
                sub_elements = element.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'section'])
                
                if sub_elements:  # サブ要素がある場合は分割
                    for sub_element in sub_elements:
                        sub_html = str(sub_element)
                        
                        # サブ要素も大きすぎる場合はさらに分割
                        if len(sub_html) > max_chunk_size:
                            sub_parts = [sub_html[i:i+max_chunk_size] for i in range(0, len(sub_html), max_chunk_size)]
                            for part in sub_parts:
                                chunks.append(part)
                        else:
                            if len(current_chunk) + len(sub_html) > max_chunk_size:
                                # 現在のチャンクが最大サイズに近づいたら保存
                                if current_chunk:
                                    chunks.append(current_chunk)
                                    current_chunk = ""
                            
                            current_chunk += sub_html
                            
                            # サブ要素を追加した後にチェック
                            if len(current_chunk) > max_chunk_size:
                                chunks.append(current_chunk)
                                current_chunk = ""
                else:  # サブ要素がない場合は単純に文字列分割
                    parts = [element_html[i:i+max_chunk_size] for i in range(0, len(element_html), max_chunk_size)]
                    chunks.extend(parts)
            else:
                # 通常の要素の場合
                if len(current_chunk) + len(element_html) > max_chunk_size:
                    chunks.append(current_chunk)
                    current_chunk = element_html
                else:
                    current_chunk += element_html
        
        # 最後のチャンクを追加
        if current_chunk:
            chunks.append(current_chunk)
        
        # チャンクが生成されなかった場合（分割できなかった場合）は、
        # 単純にHTML全体を文字数で分割（より小さなチャンクサイズを使用）
        if not chunks:
            html_str = str(soup)
            return [html_str[i:i+max_chunk_size] for i in range(0, len(html_str), max_chunk_size)]
        
        # 最終チェック: すべてのチャンクがトークン制限を超えないことを確認
        final_chunks = []
        for chunk in chunks:
            if len(chunk) > max_chunk_size:
                # 大きすぎるチャンクは更に分割
                sub_chunks = [chunk[i:i+max_chunk_size] for i in range(0, len(chunk), max_chunk_size)]
                final_chunks.extend(sub_chunks)
            else:
                final_chunks.append(chunk)
                
        return final_chunks
    
    def _process_html_chunks(self, chunks):
        """複数のHTMLチャンクをLLMで処理し、結果を結合する (レート制限対策強化版)"""
        results = []
        total_chunks = len(chunks)
        
        # トークン制限エラーが発生したときの再試行回数
        max_retries = 3
        
        print(f"合計 {total_chunks} チャンクを処理します...")
        
        for i, chunk in enumerate(chunks):
            retries = 0
            success = False
            
            while not success and retries < max_retries:
                try:
                    prompt = self.extraction_prompt.format(
                        html_content=chunk,
                        part_num=i+1,
                        total_parts=total_chunks
                    )
                    
                    # 長すぎるチャンクを検出して処理
                    if len(chunk) > 4000:
                        print(f"チャンク {i+1}/{total_chunks} はサイズが大きいため、単純な構造抽出を行います。")
                        # この場合はLLMを使わずに単純な抽出を行う
                        soup = BeautifulSoup(chunk, 'html.parser')
                        # 明らかなナビゲーション要素やスクリプトを削除
                        for nav_elem in soup.find_all(['nav', 'header', 'footer', 'script', 'style', 'noscript']):
                            nav_elem.decompose()
                        results.append(str(soup))
                    else:
                        # 通常のLLM処理
                        result = self.llm.invoke(prompt)
                        results.append(result.content.strip())
                    
                    success = True
                    
                    # レート制限を避けるための待機 (特に連続的なリクエストでは重要)
                    wait_time = 2 + (retries * 2)  # リトライごとに待機時間を増やす
                    if i < total_chunks - 1 or retries > 0:
                        print(f"レート制限を避けるため {wait_time} 秒待機します...")
                        time.sleep(wait_time)
                
                except Exception as e:
                    error_msg = str(e)
                    retries += 1
                    
                    # レート制限エラーの場合
                    if "429" in error_msg or "rate_limit" in error_msg:
                        wait_time = 15 * (2 ** retries)  # 指数バックオフ: 30秒、60秒、120秒...
                        print(f"レート制限エラーが発生しました。{wait_time}秒待機後に再試行します。({retries}/{max_retries})")
                        time.sleep(wait_time)
                        
                        # チャンクが大きすぎる場合は分割する
                        if "Request too large" in error_msg and len(chunk) > 1000:
                            print(f"チャンクが大きすぎるため分割します。")
                            half_point = len(chunk) // 2
                            # タグが切れないようにする簡易的な対応
                            split_point = chunk.rfind(">", 0, half_point) + 1
                            if split_point <= 0:
                                split_point = half_point
                                
                            first_half = chunk[:split_point]
                            second_half = chunk[split_point:]
                            
                            # 分割した最初の部分を現在のチャンクとして使用
                            chunk = first_half
                            
                            # 2つ目の部分は後ほど処理するチャンクリストに追加
                            chunks.insert(i+1, second_half)
                            total_chunks = len(chunks)
                    else:
                        print(f"チャンク {i+1}/{total_chunks} の処理中にエラーが発生しました: {error_msg}")
                        if retries < max_retries:
                            print(f"{retries}/{max_retries}回目の再試行を行います...")
                            time.sleep(5)  # 一般的なエラーの場合は短い待機
                        else:
                            # 最大再試行回数を超えた場合は、このチャンクをスキップ
                            print(f"再試行回数の上限に達したため、このチャンクをスキップします。")
                            # エラーチャンクの代わりに最小限の情報を追加
                            results.append(f"<!-- チャンク {i+1} の処理中にエラーが発生しました -->")
                            success = True  # ループを抜けるためにsuccessをTrueに
        
        print(f"全てのチャンク処理が完了しました。結果を結合しています...")
        
        # 結果を結合
        if len(results) > 1:
            # 小さな塊に分けて結合する
            consolidated_results = []
            batch_size = 5  # 一度に結合する結果の数
            
            for i in range(0, len(results), batch_size):
                batch = results[i:i+batch_size]
                fragments_text = "\n\n--- フラグメント区切り ---\n\n".join(batch)
                
                try:
                    # 断片を結合するためのプロンプト
                    consolidation_result = self.llm.invoke(
                        self.consolidation_prompt.format(html_fragments=fragments_text)
                    )
                    consolidated_results.append(consolidation_result.content.strip())
                    
                    # レート制限を避けるための待機
                    if i + batch_size < len(results):
                        print(f"バッチ結合完了 ({i+1}～{min(i+batch_size, len(results))}/{len(results)})。待機中...")
                        time.sleep(5)
                        
                except Exception as e:
                    print(f"結果バッチの結合中にエラーが発生しました: {str(e)}")
                    # エラーの場合は単純に結合して返す
                    consolidated_results.append("\n".join(batch))
            
            # 最終的な結合（必要な場合）
            if len(consolidated_results) > 1:
                try:
                    final_fragments = "\n\n--- 最終結合 ---\n\n".join(consolidated_results)
                    final_result = self.llm.invoke(
                        self.consolidation_prompt.format(html_fragments=final_fragments)
                    )
                    return final_result.content.strip()
                except Exception as e:
                    print(f"最終結合中にエラーが発生しました: {str(e)}")
                    return "\n".join(consolidated_results)
            else:
                return consolidated_results[0]
        elif results:
            return results[0]
        else:
            return "メインコンテンツを抽出できませんでした。"
    
    def extract_from_file(self, file_path):
        """HTMLファイルからメインコンテンツを抽出する"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            return self.extract_from_html(html_content)
        except Exception as e:
            return f"エラー: ファイルの読み込みに失敗しました - {str(e)}"
    
    def extract_from_url(self, url):
        """URLからコンテンツを取得してメインコンテンツを抽出する"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return self.extract_from_html(response.text)
        except Exception as e:
            return f"エラー: URLからのコンテンツ取得に失敗しました - {str(e)}"
    
    def extract_from_html(self, html_content):
        """HTML文字列からメインコンテンツを抽出する"""
        try:
            # HTMLの基本クリーニング
            cleaned_html = self._clean_html(html_content)
            
            # メインコンテンツのセレクタを識別
            selectors = self._identify_main_content_selectors(cleaned_html)
            
            # セレクタが見つかった場合、それを使用してメインコンテンツを抽出
            extracted_content = None
            if selectors:
                extracted_content = self._extract_by_selectors(cleaned_html, selectors)
            
            # セレクタでの抽出が失敗した場合や、抽出されたコンテンツが小さすぎる場合
            if not extracted_content or len(extracted_content) < 500:
                # HTMLをチャンクに分割
                chunks = self._split_html_into_chunks(cleaned_html)
                
                # チャンクごとに処理して結合
                extracted_content = self._process_html_chunks(chunks)
            
            return extracted_content
        except Exception as e:
            return f"エラー: メインコンテンツの抽出に失敗しました - {str(e)}"

    def save_to_file(self, content, output_path):
        """抽出したコンテンツをファイルに保存する"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"抽出されたコンテンツを {output_path} に保存しました。"
        except Exception as e:
            return f"エラー: ファイルの保存に失敗しました - {str(e)}"


def main():
    parser = argparse.ArgumentParser(description='WebページからLLMを使用してメインコンテンツを抽出するツール')
    
    # 入力方法の指定
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('-f', '--file', help='HTMLファイルのパス')
    input_group.add_argument('-u', '--url', help='ウェブページのURL')
    
    # 出力先の指定
    parser.add_argument('-o', '--output', help='出力ファイルのパス', default='output')
    
    # APIキーの指定（オプション）
    parser.add_argument('-k', '--api-key', help='OpenAI APIキー（指定しない場合は環境変数OPENAI_API_KEYを使用）')
    
    # モデルの指定（オプション）
    parser.add_argument('-m', '--model', help='使用するOpenAIモデル（デフォルトはgpt-4o）', default='gpt-4o')
    
    # 詳細表示オプション
    parser.add_argument('-v', '--verbose', action='store_true', help='詳細な処理情報を表示')
    
    args = parser.parse_args()
    
    
    try:
        if args.verbose:
            print(f"モデル '{args.model}' を使用してメインコンテンツの抽出を開始します...")
        
        extractor = WebContentExtractor(api_key=args.api_key, model=args.model)
        
        if args.file:
            if args.verbose:
                print(f"ファイル '{args.file}' からコンテンツを読み込み中...")
            content = extractor.extract_from_file(args.file)
        else:
            if args.verbose:
                print(f"URL '{args.url}' からコンテンツを取得中...")
            content = extractor.extract_from_url(args.url)
        
        if args.verbose:
            print(f"抽出されたコンテンツのサイズ: {len(content)} バイト")
        
        output_path = Path(args.output) / "html" 
        output_path.mkdir(parents=True, exist_ok=True) 
        output_file_path = output_path / (Path(args.file).stem + ".html")
        result_message = extractor.save_to_file(content, output_file_path)
        print(result_message)
        
    except Exception as e:
        print(f"エラーが発生しました: {str(e)}")


if __name__ == "__main__":
    main()
