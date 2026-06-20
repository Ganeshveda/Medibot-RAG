from pathlib import Path
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker

pdf_path = Path(__file__).resolve().parent.parent.parent / "mediassist_data" / "mediassist_data" / "clinical" / "drug_formulary.pdf"
print(f"Path: {pdf_path}, Exists: {pdf_path.exists()}")

converter = DocumentConverter()
result = converter.convert(pdf_path)
doc = result.document

chunker = HybridChunker(
    tokenizer="sentence-transformers/all-MiniLM-L6-v2",
    max_tokens=256,
    merge_peers=True
)

chunks = list(chunker.chunk(dl_doc=doc))
print(f"Total chunks: {len(chunks)}")

for i, chunk in enumerate(chunks):
    doc_items = getattr(chunk.meta, "doc_items", [])
    labels = [str(getattr(item, "label", "")).lower() for item in doc_items]
    is_table = any("table" in l for l in labels)
    if is_table:
        print(f"\n--- TABLE CHUNK {i+1} ---")
        print(f"Labels: {labels}")
        print(f"Headings: {chunk.meta.headings}")
        print(f"Text content preview:\n{chunk.text[:300]}")
        break
