# scripts/docai_helpers.py
import os
from google.cloud import documentai_v1 as documentai

PROJECT_ID = os.environ.get("PROJECT_ID")
LOCATION = os.environ.get("DOCAI_LOCATION", "us")  # same location used in console

def list_processors():
    client = documentai.DocumentProcessorServiceClient()
    parent = f"projects/{PROJECT_ID}/locations/{LOCATION}"
    print("Listing processors in:", parent)
    for p in client.list_processors(parent=parent):
        # p.name looks like projects/{project}/locations/{location}/processors/{processor_id}
        print("processor:", p.name, "| display_name:", p.display_name, "| type:", p.type)
    print("done")

def process_document(processor_id, file_path, mime_type="application/pdf"):
    client = documentai.DocumentProcessorServiceClient()
    name = client.processor_path(PROJECT_ID, LOCATION, processor_id)
    with open(file_path, "rb") as f:
        doc_bytes = f.read()
    raw_doc = {"content": doc_bytes, "mime_type": mime_type}
    request = {"name": name, "raw_document": raw_doc}
    result = client.process_document(request=request)
    # print a short snippet of recognized text
    text = result.document.text
    print("=== Extracted text snippet ===")
    print(text[:1200])
    return result

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "list":
        list_processors()
    elif len(sys.argv) >= 3 and sys.argv[1] == "proc":
        _, _, proc_id, file_path = sys.argv[:4]
        process_document(proc_id, file_path)
    else:
        print("Usage:\n  python scripts/docai_helpers.py list\n  python scripts/docai_helpers.py proc PROCESSOR_ID path/to/file.pdf")
