"""Bundled document runtime and deterministic conversion of embedded-font DOCX."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid
import zipfile
import importlib.util
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / '산출'
DEPENDENCIES = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies'
PYTHON = DEPENDENCIES / 'python/bin/python3'

def _tool(environment, candidates, names):
    if os.environ.get(environment):return Path(os.environ[environment]).expanduser()
    for candidate in candidates:
        if candidate.is_file():return candidate
    for name in names:
        found=shutil.which(name)
        if found:return Path(found)
    return Path('__missing_'+names[0]+'__')

SOFFICE = _tool('JAARVIS_OPINION_SOFFICE',[
    DEPENDENCIES/'native/libreoffice-headless/libreoffice/LibreOfficeDev.app/Contents/MacOS/soffice',
    Path('/Applications/LibreOffice.app/Contents/MacOS/soffice'),
    Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'LibreOffice/program/soffice.exe'],['soffice','soffice.exe'])
PDFTOPPM = _tool('JAARVIS_OPINION_PDFTOPPM',[
    DEPENDENCIES/'native/poppler/bin/pdftoppm',DEPENDENCIES/'bin/override/pdftoppm'],['pdftoppm','pdftoppm.exe'])
PACKAGES=['docx','pypdf','pdfplumber','reportlab','PIL','numpy','lxml']
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
FONT_CONTENT_TYPE = 'application/vnd.openxmlformats-officedocument.obfuscatedFont'


def bootstrap() -> None:
    """Select a complete document environment without looping between incomplete ones."""
    configured=os.environ.get('JAARVIS_OPINION_PYTHON')
    if configured:
        if Path(configured).resolve()!=Path(sys.executable).resolve():
            os.execv(configured,[configured,*sys.argv])
        return
    if all(importlib.util.find_spec(name) is not None for name in PACKAGES):return
    candidates=[HERE/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python'),PYTHON]
    probe='import importlib.util,sys;sys.exit(not all(importlib.util.find_spec(n) is not None for n in '+repr(PACKAGES)+'))'
    for candidate in candidates:
        if candidate.is_file() and candidate.resolve()!=Path(sys.executable).resolve():
            ready=subprocess.run([str(candidate),'-c',probe],capture_output=True,timeout=15)
            if ready.returncode==0:os.execv(str(candidate),[str(candidate),*sys.argv])


def open_document(path):
    """Open a local artifact using the operating system's file association."""
    if os.name=='nt':os.startfile(str(Path(path).resolve()))
    elif sys.platform=='darwin':subprocess.run(['open',str(path)],check=False)
    elif shutil.which('xdg-open'):subprocess.run(['xdg-open',str(path)],check=False)


def require_packages():
    missing=[name for name in PACKAGES if importlib.util.find_spec(name) is None]
    if missing:raise RuntimeError('문서 패키지 미설치: '+', '.join(missing)+'. requirements.txt와 설치 안내를 확인하세요.')


def temp_root() -> Path:
    path = OUT / '_tmp'
    path.mkdir(parents=True, exist_ok=True)
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def obfuscate(data: bytes, font_key: str) -> bytes:
    """ECMA-376 17.8.1: reverse GUID bytes, XOR the first two 16-byte blocks."""
    key = uuid.UUID(font_key.strip('{}')).bytes[::-1]
    result = bytearray(data)
    for index in range(min(32, len(result))):
        result[index] ^= key[index % 16]
    return bytes(result)


def embedding_rights(data: bytes) -> int:
    count = struct.unpack_from('>H', data, 4)[0]
    for index in range(count):
        tag, _, offset, _ = struct.unpack_from('>4sIII', data, 12 + index * 16)
        if tag == b'OS/2':
            return struct.unpack_from('>H', data, offset + 8)[0]
    raise ValueError('글꼴의 임베딩 권한 정보를 찾을 수 없습니다.')


def embed_fonts(docx_path: Path, fonts: dict[str, Path]) -> None:
    """Add editable, full-font embedding; never install fonts or change system settings."""
    from lxml import etree
    with zipfile.ZipFile(docx_path) as source:
        entries = {info.filename: source.read(info.filename) for info in source.infolist()}
    table = etree.fromstring(entries['word/fontTable.xml'])
    relationships = etree.Element(f'{{{REL}}}Relationships', nsmap={None: REL})
    for number, (family, font_path) in enumerate(fonts.items(), 1):
        data = Path(font_path).read_bytes()
        flags = embedding_rights(data)
        if flags & (0x2 | 0x200) or (flags & 0x4 and not flags & 0x8):
            raise ValueError('편집 가능한 글꼴 임베딩이 허용되지 않습니다: ' + family)
        key = '{' + str(uuid.uuid5(uuid.NAMESPACE_OID, hashlib.sha256(data).hexdigest())).upper() + '}'
        font = next((x for x in table if x.get(f'{{{W}}}name') == family), None)
        if font is None:
            font = etree.SubElement(table, f'{{{W}}}font', {f'{{{W}}}name': family})
        for child in list(font):
            if child.tag.rsplit('}', 1)[-1].startswith('embed'):
                font.remove(child)
        rid = 'rIdOpinionFont' + str(number)
        etree.SubElement(font, f'{{{W}}}embedRegular', {f'{{{R}}}id': rid, f'{{{W}}}fontKey': key, f'{{{W}}}subsetted': '0'})
        target = f'fonts/opinion{number}.odttf'
        etree.SubElement(relationships, f'{{{REL}}}Relationship', {'Id': rid, 'Type': R + '/font', 'Target': target})
        entries['word/' + target] = obfuscate(data, key)
    settings = etree.fromstring(entries['word/settings.xml'])
    for tag in ['embedTrueTypeFonts', 'embedSystemFonts']:
        if settings.find(f'{{{W}}}' + tag) is None:
            etree.SubElement(settings, f'{{{W}}}' + tag)
    ctypes = etree.fromstring(entries['[Content_Types].xml'])
    ct_ns = 'http://schemas.openxmlformats.org/package/2006/content-types'
    if not any(n.get('Extension') == 'odttf' for n in ctypes):
        etree.SubElement(ctypes, f'{{{ct_ns}}}Default', {'Extension': 'odttf', 'ContentType': FONT_CONTENT_TYPE})
    for name, node in [('word/fontTable.xml', table), ('word/_rels/fontTable.xml.rels', relationships), ('word/settings.xml', settings), ('[Content_Types].xml', ctypes)]:
        entries[name] = etree.tostring(node, xml_declaration=True, encoding='UTF-8', standalone=True)
    with zipfile.ZipFile(docx_path, 'w', zipfile.ZIP_DEFLATED) as target:
        for name, data in entries.items():
            target.writestr(name, data)


def extract_fonts(docx_path: Path, output: Path) -> dict[str, Path]:
    """Use embedded fonts only for rendering this document in the local temporary directory."""
    output.mkdir(parents=True, exist_ok=True)
    result = {}
    with zipfile.ZipFile(docx_path) as source:
        rels = ET.fromstring(source.read('word/_rels/fontTable.xml.rels'))
        targets = {r.get('Id'): r.get('Target') for r in rels}
        for font in ET.fromstring(source.read('word/fontTable.xml')):
            embedded = font.find(f'{{{W}}}embedRegular')
            if embedded is None:
                continue
            target = targets[embedded.get(f'{{{R}}}id')]
            if '..' in Path(target).parts or not target.startswith('fonts/'):
                raise ValueError('글꼴 파트 경로 오류')
            data = obfuscate(source.read('word/' + target), embedded.get(f'{{{W}}}fontKey'))
            if data[:4] not in (b'\x00\x01\x00\x00', b'OTTO'):
                raise ValueError('임베딩 글꼴 디코딩 오류')
            path = output / (Path(target).stem + '.ttf')
            path.write_bytes(data)
            result[font.get(f'{{{W}}}name')] = path
    if not result:
        raise ValueError('필수 임베딩 글꼴이 없습니다.')
    return result


def convert_docx(docx_path: Path, pdf_path: Path, work_dir: Path | None = None) -> dict:
    require_packages()
    from pypdf import PdfReader
    if not SOFFICE.is_file():
        raise RuntimeError('LibreOffice 변환기를 찾을 수 없습니다. 설치하거나 JAARVIS_OPINION_SOFFICE로 지정하세요.')
    docx_path, pdf_path = Path(docx_path).resolve(), Path(pdf_path).resolve()
    with tempfile.TemporaryDirectory(prefix='docx_pdf_', dir=work_dir or temp_root()) as directory:
        tmp = Path(directory)
        fonts = extract_fonts(docx_path, tmp / 'fonts')
        fontconfig = tmp / 'fonts.conf'
        # Fontconfig is scoped to this conversion; no global font or preference writes.
        conf = ET.Element('fontconfig')
        ET.SubElement(conf, 'dir').text = str(tmp / 'fonts')
        ET.SubElement(conf, 'cachedir').text = str(tmp / 'fontcache')
        fontconfig.write_bytes(ET.tostring(conf, encoding='UTF-8', xml_declaration=True))
        profile = tmp / 'profile'
        env = os.environ.copy()
        env.update({'FONTCONFIG_FILE': str(fontconfig), 'TMPDIR': str(tmp),
                    'XDG_CACHE_HOME': str(tmp / 'cache'), 'XDG_CONFIG_HOME': str(tmp / 'config')})
        cmd = [str(SOFFICE), '-env:UserInstallation=' + profile.as_uri(), '--headless', '--invisible',
               '--norestore', '--nodefault', '--nolockcheck', '--convert-to', 'pdf:writer_pdf_Export',
               '--outdir', str(tmp), str(docx_path)]
        process = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
        generated = tmp / (docx_path.stem + '.pdf')
        if process.returncode or not generated.is_file():
            raise RuntimeError('DOCX→PDF 변환 실패: ' + (process.stdout + process.stderr)[-1500:])
        reader = PdfReader(generated)
        if not reader.pages:
            raise RuntimeError('DOCX 변환 결과가 비어 있습니다.')
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(generated, pdf_path)
        return {'engine': str(SOFFICE), 'docx_sha256': sha256(docx_path), 'pages': len(reader.pages),
                'font_sha256': {name: sha256(path) for name, path in fonts.items()}}


def render_pdf(pdf_path: Path, output: Path, dpi: int = 120, first: int | None = None, last: int | None = None) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    executable = PDFTOPPM
    if not executable.is_file():raise RuntimeError('pdftoppm을 설치하거나 JAARVIS_OPINION_PDFTOPPM으로 지정하세요.')
    command = [str(executable), '-r', str(dpi), '-png']
    if first is not None:
        command += ['-f', str(first)]
    if last is not None:
        command += ['-l', str(last)]
    command += [str(Path(pdf_path).resolve()), str(output / 'page')]
    subprocess.run(command, check=True, capture_output=True, timeout=60)
    return sorted(output.glob('page-*.png'), key=lambda p: int(p.stem.split('-')[-1]))
