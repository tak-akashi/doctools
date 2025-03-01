import os
from pathlib import Path
from dotenv import load_dotenv

import pdfplumber
import base64
from pdf2image import convert_from_path

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient

load_dotenv()


class PDF2MarkdownLLM:
    """PDFドキュメントをLLMを使ってmarkdown形式に変換するクラス"""

    def __init__(self, llm: ChatOpenAI, pdf_path: str, output_dir: str="output"):
        self.llm = llm
        self.pdf_path = Path(pdf_path)
        self.output_path = Path(output_dir) / Path(pdf_path).stem
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.markdown = ""

    def convert_to_text(self):
        with pdfplumber.open(self.pdf_path) as pdf:
            output_text_path = self.output_path / "text"
            output_text_path.mkdir(parents=True, exist_ok=True)            
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                with open(self.output_path / f"text/{i}.txt", "w") as f:
                    f.write(text)

    def convert_to_image(self):
        output_image_path = self.output_path / "image"
        output_image_path.mkdir(parents=True, exist_ok=True)           
        images = convert_from_path(self.pdf_path)
        for i, image in enumerate(images, start=1):

            image.save(self.output_path / f"image/{i}.png")

    def encode_image(self, image_path: Path):
        with image_path.open("rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    
    def save(self, output_path, text: str):
        with open(output_path, "w") as f:
            f.write(text)

   
    def generate_markdown_by_page(self, text: str, image_path: Path):
        """PDFのページごとのテキストと画像を受け取り、markdown形式のドキュメントを生成する"""

        prompt =  """
        # Task
        ユーザーからの入力として、解析対象の日本語で書かれたドキュメントの特定ページの画像（ページ画像情報）とPDFから抽出した同じページのテキスト（ページテキスト情報）がページ順に1ページずつ提供されます。
        テキストと画像から、以下のルールに従ってmarkdown形式のドキュメントを生成してください。

        # Rules
        - ドキュメント構成の把握能力はあなたは優れていますが、OCR性能についてはPDFから抽出したページテキスト情報の方が正確です。
          したがって、文字情報の取得についてはPDFから抽出したページテキスト情報を優先してください。
        - ページ画像情報から表が読み取れる場合は、ページ画像情報とテキストの情報を双方を利用してmarkdownで表を再現してください。
          markdown形式の表で内容を再現することが難しい場合は、箇条書きで内容を再現してください。
        - ページ画像情報からページの一部に画像があることが読み取れる場合は、ページ画像情報を利用して画像の説明を箇条書きで作成してください。
        - ページ画像情報からグラフが読み取れる場合は、グラフの種類とその内容を箇条書きで作成してください。
        
        # Output
        - markdwon形式で出力してください。
        - markdown を示す文字列（```markdown```）は出力しないでください。
        - ページ画像全体ではなく、ページの一分に画像があり、その画像の説明をする場合には、そこに画像があったことがわかるよう、画像の説明の前に「[画像]」という文字列を入れてください。
        
        # Input
        ## ページテキスト情報
        {text}
        ## ページ画像情報
        """
        # 画像をbase64にエンコード
        base64_image = self.encode_image(image_path)
        # APIに送信するメッセージ
        messages = HumanMessage(
            content = [
                {"type": "text", "text": prompt.format(text=text)},
                {
                    "type": "image_url", 
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                }
            ]
        )
        response = self.llm.invoke([messages])
        return response.content

    def consolidate_markdown(self):
        """頁ごとのmarkdownを結合して、最終的なmarkdownを生成する"""
        md_files = list(self.output_path.glob("markdown/*.md"))
        md_files.sort(key=lambda x: int(x.stem))
        for md_file in md_files:
            with open(md_file) as f:
                self.markdown += f.read() + "\n\n"
    
    def run(self):
        """PDFドキュメントをmarkdown形式に変換する（一連のプロセスの実行）"""
        self.convert_to_text()
        self.convert_to_image()
        with pdfplumber.open(self.pdf_path) as pdf:
            page_count = len(pdf.pages)
        for i, page_num in enumerate(range(1, page_count + 1), start=1):
            with open(self.output_path / f"text/{page_num}.txt") as f:
                text = f.read()
            image_path = self.output_path / f"image/{page_num}.png"
            markdown = self.generate_markdown_by_page(text, image_path)
            output_md_path = self.output_path / f"markdown"
            output_md_path.mkdir(parents=True, exist_ok=True)
            self.save(output_md_path / f"{page_num}.md", markdown)
        self.consolidate_markdown()
        self.save(self.output_path / "output_by_llm.md", self.markdown)
        print(f"Markdown形式のドキュメントを {self.output_path / 'output_by_llm.md'} に保存しました。")


class PDF2MarkdownAzureDI:
    """PDFドキュメントをAzure Document Intelligenceを使ってmarkdown形式に変換するクラス"""

    def __init__(self, 
                 client: DocumentIntelligenceClient, 
                 pdf_path: str, 
                 output_dir: str="output"):
        
        self.client = client
        self.pdf_path = Path(pdf_path)
        self.output_path = Path(output_dir) / Path(pdf_path).stem
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.markdown = ""

    def convert_pdf_to_md(self):
        with self.pdf_path.open("rb") as f:
            poller = self.client.begin_analyze_document(
                model_id="prebuilt-layout",  # 使用するモデルID
                body=f,
                output_content_format="markdown"
            )
            result = poller.result()
        self.markdown = result.content

    def save_md_file(self):
        with (self.output_path / "output_by_azure_di.md").open("w") as f:
            f.write(self.markdown)

    def run(self):
        self.convert_pdf_to_md()
        self.save_md_file()
        print(f"Markdown形式のドキュメントを {self.output_path / 'output_by_azure_di.md'} に保存しました。")


def process(pdf_path: str, output_dir: str="output", method: str="llm"):
    if method == "llm":
        llm = ChatOpenAI(
            model="gpt-4o",
            api_key=os.getenv("OPENAI_API_KEY")
        )
        pdf2markdown = PDF2MarkdownLLM(llm, pdf_path, output_dir)
        pdf2markdown.run()
    elif method == "di":
        client = DocumentIntelligenceClient(
            endpoint=os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"),
            credential=AzureKeyCredential(os.getenv("AZURE_DOCUMENT_INTELLIGENCE_API_KEY"))
        )
        pdf2markdown = PDF2MarkdownAzureDI(client, pdf_path, output_dir)
        pdf2markdown.run()
    else:
        raise ValueError("methodはllmかdiを指定してください")


if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path", type=str, help="PDFのファイルパスを指定する")
    parser.add_argument("--output_dir", "-o", type=str, default="output", help="出力先ディレクトリを指定する")
    parser.add_argument("--method", "-m", choices=["llm", "di"], default="llm", help="使用する手法を指定する")
    args = parser.parse_args()

    process(args.pdf_path, args.output_dir, args.method)
