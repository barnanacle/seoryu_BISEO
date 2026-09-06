"""Check the local opinion document runtime without installing anything."""
from document_runtime import bootstrap
if __name__=='__main__':
    bootstrap()
    import importlib.util,json,platform,sys
    from importlib.metadata import version,PackageNotFoundError
    from document_runtime import SOFFICE,PDFTOPPM,PACKAGES,HERE
    packages={}
    for module,distribution in [('docx','python-docx'),('pypdf','pypdf'),('pdfplumber','pdfplumber'),('reportlab','reportlab'),('PIL','Pillow'),('numpy','numpy'),('lxml','lxml')]:
        try:packages[distribution]=version(distribution)
        except PackageNotFoundError:packages[distribution]=None
    result={'python':sys.version.split()[0],'platform':platform.system(),'packages':packages,
            'libreoffice_available':SOFFICE.is_file(),'pdftoppm_available':PDFTOPPM.is_file(),
            'template_available':(HERE/'서식/별지_상세의견서_템플릿.docx').is_file()}
    result['ready']=sys.version_info>=(3,10) and all(packages.values()) and all(result[k] for k in ['libreoffice_available','pdftoppm_available','template_available'])
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result['ready']:print('문서 환경이 부족합니다. README의 설치 방법과 환경변수 안내를 확인하세요.')
    raise SystemExit(0 if result['ready'] else 1)
