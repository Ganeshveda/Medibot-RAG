import sys
from pathlib import Path
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker

# Path to a test PDF
pdf_path = Path(__file__).resolve().parent.parent.parent / "mediassist_data" / "mediassist_data" / "general" / "code_of_conduct.pdf"
print(f"Test PDF path: {pdf_path}")
print(f"Exists: {pdf_path.exists()}")

converter = DocumentConverter()
print("Converting PDF with Docling...")
result = converter.convert(pdf_path)
doc = result.document

print("Initializing HybridChunker...")
# We use sentence-transformers/all-MiniLM-L6-v2 as the tokenizer model
chunker = HybridChunker(
    tokenizer="sentence-transformers/all-MiniLM-L6-v2",
    max_tokens=256, # The PRD mentions embedding sequence length is 256 tokens max
    merge_peers=True
)

print("Chunking document...")
chunks = list(chunker.chunk(dl_doc=doc))
print(f"Total chunks generated: {len(chunks)}")

for i, chunk in enumerate(chunks[:5]):
    print(f"\n--- CHUNK {i+1} ---")
    print(f"Text content:\n{chunk.text}")
    print(f"Metadata headings: {getattr(chunk.meta, 'headings', None)}")
    print(f"Doc items: {getattr(chunk.meta, 'doc_items', None)}")
    # Inspect other fields
    print(f"Chunk attributes: {dir(chunk)}")
    print(f"Meta attributes: {dir(chunk.meta)}")
