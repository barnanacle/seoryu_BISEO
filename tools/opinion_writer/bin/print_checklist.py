#!/usr/bin/env python3
"""Print a local Markdown questionnaire through the same DOCX/PDF runtime."""
from document_runtime import bootstrap
if __name__=='__main__':
    bootstrap()
    import argparse
    from pathlib import Path
    from build_pdf import HERE,OUTDIR,checked_output
    from text_document import write_text_document
    from document_runtime import convert_docx
    p=argparse.ArgumentParser();p.add_argument('markdown',nargs='?',default=str(HERE/'상담_체크리스트.md'));p.add_argument('--out-dir',default=str(OUTDIR/'상담준비'));a=p.parse_args()
    out=checked_output(a.out_dir);stem=Path(a.markdown).stem;n=1;target=out/stem
    while target.with_suffix('.pdf').exists() or target.with_suffix('.docx').exists():
        n+=1;target=out/(stem+'_v%03d'%n)
    write_text_document(Path(a.markdown).read_text(encoding='utf-8'),target.with_suffix('.docx'))
    convert_docx(target.with_suffix('.docx'),target.with_suffix('.pdf'))
    print(target.with_suffix('.pdf'))
