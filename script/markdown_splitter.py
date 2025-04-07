from langchain_text_splitters.markdown import MarkdownHeaderTextSplitter

def split_markdown_with_langchain(markdown_text, max_chunk_size=1800):
    # ヘッダーレベルとその分割設定
    headers_to_split_on = [
        ("#", "header1"),
        ("##", "header2"),
        ("###", "header3"),
    ]
    
    # MarkdownHeaderTextSplitterでヘッダーに基づいて分割（ヘッダーを残す）
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False  # ヘッダーをテキスト内に残す
    )
    header_splits = markdown_splitter.split_text(markdown_text)
    
    # 最終的なチャンク配列
    final_chunks = []
    current_chunk = ""
    
    for doc in header_splits:
        # セクションの内容を取得（ヘッダーは既に含まれている）
        section_content = doc.page_content
        
        # 現在のチャンクにセクションを追加するとサイズを超えるかチェック
        if len(current_chunk) + len(section_content) <= max_chunk_size:
            # サイズを超えなければ現在のチャンクに追加
            if current_chunk and not current_chunk.endswith("\n"):
                current_chunk += "\n"
            current_chunk += section_content
        else:
            # サイズを超える場合は、現在のチャンクを確定し新しいチャンクを開始
            if current_chunk:  # 空でない場合のみ追加
                final_chunks.append(current_chunk)
            current_chunk = section_content
    
    # 最後のチャンクを追加
    if current_chunk:
        final_chunks.append(current_chunk)
    
    return final_chunks


def main():
    # 使用例
    markdown_text = """# 大見出し
    これは最初の段落です。
    ## 中見出し
    これは中見出しの下の段落です。
    ### 小見出し
    これは小見出しの下の段落です。長い文章が続きます...
    """

    chunks = split_markdown_with_langchain(markdown_text, max_chunk_size=30)
    for i, chunk in enumerate(chunks):
        print(f"チャンク {i+1}:")
        print(chunk)
        print(f"チャンクサイズ: {len(chunk)} 文字")
        print("-" * 50)

        
if __name__ == "__main__":
    main()

