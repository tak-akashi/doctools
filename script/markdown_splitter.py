from langchain.text_splitter import MarkdownHeaderTextSplitter

def split_markdown_with_langchain(markdown_text, max_chunk_size=1800):
    # ヘッダーレベルとその分割設定
    headers_to_split_on = [
        ("#", "header1"),
        ("##", "header2"),
        ("###", "header3"),
    ]
    
    # MarkdownHeaderTextSplitterでヘッダーに基づいて分割
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on
    )
    header_splits = markdown_splitter.split_text(markdown_text)
    
    # 最終的なチャンク配列
    final_chunks = []
    current_chunk = ""
    
    for doc in header_splits:
        # メタデータからヘッダー情報を取得
        header_info = ""
        for header_level in ["header1", "header2", "header3"]:
            if header_level in doc.metadata and doc.metadata[header_level]:
                level_num = int(header_level[-1])
                header_info += "#" * level_num + " " + doc.metadata[header_level] + "\n"
        
        # セクションの内容を取得（ヘッダー + 内容）
        section_content = header_info + doc.page_content
        
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

    chunks = split_markdown_with_langchain(markdown_text)
    for i, chunk in enumerate(chunks):
        print(f"チャンク {i+1}:")
        print(chunk)
        print(f"チャンクサイズ: {len(chunk)} 文字")
        print("-" * 50)
        
        
if __name__ == "__main__":
    main()

