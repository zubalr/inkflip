"""Bounded independent observations; never writes generator expectations."""
import hashlib
import io
import json
from pathlib import Path

import pypdf
import pypdfium2 as pdfium
from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent


def observe(entry):
    path = ROOT / 'fixtures' / entry['path']
    result = {'path': entry['path'], 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    try:
        reader = pypdf.PdfReader(io.BytesIO(path.read_bytes()))
        result['encrypted'] = reader.is_encrypted
        if reader.is_encrypted:
            result['empty_unlock'] = int(reader.decrypt(''))
            result['fixture_unlock'] = int(reader.decrypt('fixture'))
        result['pages'] = len(reader.pages)
        result['raw_text'] = [page.extract_text() for page in reader.pages]
    except Exception as error:
        result['reader_error'] = type(error).__name__ + ': ' + str(error)
    prefix = OUT / 'renders' / path.stem
    try:
        credential = 'fixture' if 'encrypted' in path.stem else None
        with pdfium.PdfDocument(path, password=credential) as document:
            page = document[0]
            scale = 512 / max(page.get_size())
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil()
            assert max(image.size) <= 513
            image.save(prefix.with_suffix('.png'))
            result['dimensions'] = image.size
            result['png'] = str(prefix.with_suffix('.png').relative_to(ROOT))
            result['scale'] = scale
            result['render_exit'] = 0
            bitmap.close()
            page.close()
    except Exception as error:
        result['render_exit'] = 1
        result['render_error'] = type(error).__name__ + ': ' + str(error)
    return result


def sheet(results):
    rendered = [r for r in results if 'png' in r]
    canvas = Image.new('RGB', (960, ((len(rendered) + 2) // 3) * 220), '#ddd')
    draw = ImageDraw.Draw(canvas)
    for i, result in enumerate(rendered):
        x, y = (i % 3) * 320, (i // 3) * 220
        with Image.open(ROOT / result['png']) as image:
            image.thumbnail((300, 190))
            canvas.paste(image, (x, y + 25))
        draw.text((x + 4, y + 4), Path(result['path']).stem, fill='black')
    canvas.save(OUT / 'priority-contact-sheet.png')


def main():
    (OUT / 'renders').mkdir(exist_ok=True)
    manifest = json.loads((ROOT / 'fixtures/manifest.json').read_text())
    results = [observe(e) for e in manifest['entries'] if e['recipe'].get('version') == 'g78.1' and e['path'].endswith('.pdf')]
    index = {Path(r['path']).stem: r for r in results}
    assert index['bad-pdf-encrypted']['empty_unlock'] == 0
    assert index['bad-pdf-encrypted']['fixture_unlock'] > 0
    assert index['bad-pdf-encrypted']['raw_text'] == ['$100']
    assert index['bad-pdf-truncated']['render_exit'] != 0
    assert index['bad-pdf-malformed']['render_exit'] != 0
    assert index['duplicates-four']['raw_text'][0].count('$100') == 4
    for variant in ('absent', 'malformed'):
        first = Image.open(ROOT / index['mapping-missing-control']['png']).convert('RGB')
        second = Image.open(ROOT / index['mapping-missing-' + variant]['png']).convert('RGB')
        assert ImageChops.difference(first, second).getbbox() is None
    def ink(stem):
        with Image.open(ROOT / index[stem]['png']) as image:
            return sum(value < 128 for value in image.convert('L').get_flattened_data())
    assert ink('white-contrast-white') == ink('paint-order-after') == ink('unreadable-blank') == 0
    assert ink('white-contrast-control') > 1000
    assert 0 < ink('partial-clip-partial') < ink('partial-clip-control')
    assert 0 < ink('partial-clip-triangle') < ink('partial-clip-control')
    assert ink('unreadable-noise') > 1000
    (OUT / 'reader-render-observations.json').write_text(json.dumps({'pypdf': pypdf.__version__, 'pdfium': str(pdfium.PDFIUM_INFO), 'pypdfium2': str(pdfium.PYPDFIUM_INFO), 'results': results}, indent=2) + '\n')
    sheet(results)
    print(f'{len(results)} PDFs observed; encryption, rejection, duplicate and mapping-pixel assertions passed')


if __name__ == '__main__':
    main()
