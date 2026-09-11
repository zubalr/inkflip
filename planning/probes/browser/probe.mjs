// Executable feasibility source, deliberately not claimed executed in planning.
import * as pdfjs from './node_modules/pdfjs-dist/legacy/build/pdf.mjs';
pdfjs.GlobalWorkerOptions.workerSrc=new URL('./node_modules/pdfjs-dist/legacy/build/pdf.worker.mjs',import.meta.url).href;
const input=document.querySelector('#file'),canvas=document.querySelector('#page'),status=document.querySelector('#status'),output=document.querySelector('#result'),ocrButton=document.querySelector('#ocr');
let generation=0,loading=null,renderTask=null,ocr=null;
async function clear(){const next=++generation;ocrButton.disabled=true;renderTask?.cancel();renderTask=null;const oldLoading=loading,oldOcr=ocr;loading=null;ocr=null;canvas.width=0;canvas.height=0;output.textContent='';await Promise.allSettled([oldLoading?.destroy(),oldOcr?.terminate()]);return next;}
document.querySelector('#cancel').addEventListener('click',async()=>{const g=await clear();if(g===generation)status.textContent='Cancelled. References cleared; not forensic erasure.';});
input.addEventListener('change',async()=>{
 const file=input.files?.[0];const g=await clear();if(!file||g!==generation)return;
 try{
  if(file.size>20*1024*1024)throw new Error('File exceeds20MiB probe limit');
  status.textContent='Loading local bytes…';const bytes=new Uint8Array(await file.arrayBuffer());if(g!==generation)return;
  if(new TextDecoder().decode(bytes.subarray(0,5))!=='%PDF-')throw new Error('Not a supported PDF header');
  loading=pdfjs.getDocument({data:bytes,isEvalSupported:false,useSystemFonts:false,disableAutoFetch:true,cMapUrl:new URL('./node_modules/pdfjs-dist/cmaps/',import.meta.url).href,cMapPacked:true,standardFontDataUrl:new URL('./node_modules/pdfjs-dist/standard_fonts/',import.meta.url).href,wasmUrl:new URL('./node_modules/pdfjs-dist/wasm/',import.meta.url).href});
  const doc=await loading.promise;if(g!==generation)return;const page=await doc.getPage(1);const v=page.getViewport({scale:1});const scale=Math.min(2,Math.sqrt(4e6/(v.width*v.height)),8192/v.width,8192/v.height);const viewport=page.getViewport({scale});canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);canvas.style.maxWidth='100%';canvas.style.height='auto';
  const text=await page.getTextContent();if(g!==generation)return;output.textContent=`PDF.js ${pdfjs.version}\n`+text.items.filter(x=>'str'in x).map(x=>x.str).join('\n');
  renderTask=page.render({canvasContext:canvas.getContext('2d'),canvas,viewport});await renderTask.promise;if(g!==generation)return;
  status.textContent=`Rendered page1 of${doc.numPages}; other pages not checked. ${canvas.width}×${canvas.height} pixels.`;ocrButton.disabled=false;
 }catch(e){if(g===generation)status.textContent=`Failed: ${e.name}: ${e.message}`;}
});
ocrButton.addEventListener('click',async()=>{
 const g=generation;ocrButton.disabled=true;
 try{
  status.textContent='Preparing explicit local OCR assets…';const worker=await globalThis.Tesseract.createWorker('eng',1,{workerPath:new URL('./node_modules/tesseract.js/dist/worker.min.js',import.meta.url).href,corePath:new URL('./node_modules/tesseract.js-core/',import.meta.url).href,langPath:new URL('./assets/',import.meta.url).href,gzip:false,cacheMethod:'none',workerBlobURL:false});
  if(g!==generation){await worker.terminate();return;}ocr=worker;
  const result=await worker.recognize(canvas,{}, {text:true,blocks:true});if(g!==generation)return;
  output.textContent+='\n\nTesseract.js7.0.0 · rendered first page · eng\n'+result.data.text;status.textContent='OCR finished. These are readings, not ground truth.';
 }catch(e){if(g===generation)status.textContent=`OCR unavailable/failed: ${e.message}`;}
 finally{if(g===generation)ocrButton.disabled=false;}
});
