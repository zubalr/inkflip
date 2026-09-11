#!/usr/bin/env python3
"""Render and interact with labeled HTML reference locally; no actual PDF/OCR app claim."""
from __future__ import annotations
import http.server, threading, json, platform, importlib.metadata, shutil, base64
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT),**kwargs)
    def log_message(self,*args):pass

def main():
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();origin=f'http://127.0.0.1:{server.server_port}'
    receipts=[];requests=[];errors=[]
    # Controlled local DOM rendering does not navigate around browser network policy.
    # All bytes below are generated assets already available in this package.
    source=(ROOT/'reference/index.html').read_text()
    source=source.replace('<link rel="stylesheet" href="./reference.css">','<style>'+(ROOT/'reference/reference.css').read_text()+'</style>')
    image=base64.b64encode((ROOT/'probes/results/amount-crop.png').read_bytes()).decode()
    source=source.replace('../probes/results/amount-crop.png','data:image/png;base64,'+image)
    report=json.loads((ROOT/'contracts/examples/valid/native-evidence.inkflip.json').read_text())
    init='globalThis.__PREPARED_REFERENCE_REPORT__='+json.dumps(report).replace('<','\\u003c')+';'
    source=source.replace('<script src="./reference.js" defer></script>','<script>'+init+(ROOT/'reference/reference.js').read_text()+'</script>')
    try:
        with sync_playwright() as p:
            executable=shutil.which('chromium') or shutil.which('chromium-browser')
            browser=p.chromium.launch(executable_path=executable,headless=True,args=['--no-sandbox'])
            version=browser.version
            for name,width,height in [('desktop',1440,1000),('mobile',390,844),('minimum',320,844)]:
                page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
                page.on('request',lambda r: requests.append({'path':urlsplit(r.url).path,'same_origin':r.url.startswith(origin+'/')}))
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_content(source,wait_until='load');page.locator('#native-reading').filter(has_text='$1,000').wait_for(state='attached')
                assert page.locator('.reference-note').inner_text().find('not live browser processing')>=0
                overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth');assert not overflow,name
                page.screenshot(path=str(ROOT/f'reference/{name}.png'),full_page=False)
                crop=page.locator('.amount-crop').bounding_box();tab=page.locator('#tab-page').bounding_box()
                page.locator('#tab-reading').click();assert page.locator('#reading-view').is_visible() and not page.locator('#paper-view').is_visible()
                assert page.locator('#native-reading').inner_text()=='$1,000'
                page.locator('#tab-reading').press('ArrowRight');assert page.locator('#tab-compare').get_attribute('aria-selected')=='true'
                page.locator('#finding').click();assert page.locator('#finding-detail').is_visible()
                page.locator('#export').click();assert page.locator('#dialog').is_visible();assert 'Excluded:' in page.locator('#dialog-body').inner_text()
                assert page.locator('#dialog-body a').count()==2
                if name=='desktop':page.screenshot(path=str(ROOT/'reference/export-preview.png'))
                page.keyboard.press('Escape');assert not page.locator('#dialog').is_visible();assert page.locator('#export').evaluate('(e)=>e===document.activeElement')
                receipts.append({'profile':name,'viewport':[width,height],'outer_horizontal_overflow':overflow,'mode_switches':True,'keyboard_tabs':True,'export_dialog_escape_focus':True,'initial_crop_box':crop,'initial_tab_box':tab,'initial_crop_and_tabs_in_view':crop['y']+crop['height']<=height and tab['y']+tab['height']<=height})
                page.close()
            page=browser.new_page(viewport={'width':390,'height':844},reduced_motion='reduce');page.set_content(source,wait_until='load');motion=page.locator('.sample').first.evaluate('(e)=>getComputedStyle(e).transitionDuration');assert motion=='0s';page.close();browser.close()
    finally:server.shutdown();server.server_close()
    result={'status':'passed' if not errors and all(x['same_origin'] for x in requests) else 'failed','scope':'Local DOM-rendered HTML interaction reference only; CSS/PNG/report inlined from package. Initial localhost navigation blocked by browser administration policy. No live PDF.js/OCR, static-host navigation or production privacy proof.','environment':{'python':platform.python_version(),'playwright':importlib.metadata.version('playwright'),'chromium':version,'sandbox':'container Chromium launched --no-sandbox; not a security isolation test'},'profiles':receipts,'reduced_motion_transition':motion,'requests':requests,'page_errors':errors,'visual_inspection':'screenshots captured; separate human/model visual inspection required'}
    (ROOT/'probes/results/reference-probe.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
