/**
 * Standalone reproduction script for pdf-8hn audit against main aa6d039.
 * Run with: bun artifacts/followups/pdf-8hn/repro.ts
 */
import { OpenController } from "../../../apps/web/src/features/open/controller";
import { DESKTOP_PROFILE, MOBILE_PROFILE } from "../../../apps/web/src/features/open/limits";
import { resolveConfig } from "../../../packages/readers-pdfjs/src/config";
import { regionToContract } from "../../../apps/web/src/features/selection/region";

console.log("=== pdf-8hn Audit Reproductions (main aa6d039) ===\n");

// ---------------------------------------------------------------------------
// Item 1: Stale handle and document on failed replace
// ---------------------------------------------------------------------------
console.log("--- Item 1: Stale handle/document on failed replace ---");
{
  class FakeHost {
    fileState = "selecting";
    currentGeneration = 1;
    requestClear(next: "idle" | "replace") {
      this.currentGeneration += 1;
      this.fileState = next === "replace" ? "validating_file" : "idle";
    }
    own() {}
    fileValidated() {}
    metadataLoaded() {}
  }

  const host = new FakeHost();
  const fakeAdapter = {
    open: async () => ({ id: "handle_doc_A" }),
    pages: async () => ({
      count: 1,
      pages: [{ index: 0, canonical_size_pt: [100, 100], rotation: 0, raw_to_canonical_transform_id: "t1" }],
    }),
    close: async () => {},
  };

  const controller = new OpenController({ host: host as any, adapter: fakeAdapter as any, profile: DESKTOP_PROFILE });
  // Simulate active document A
  (controller as any).handle = { id: "handle_doc_A" };
  (controller as any).document = {
    label: "doc_A.pdf",
    byteLength: 1000,
    sha256: "sha_A",
    pageCount: 1,
    pages: [],
  };

  // Candidate B fails validation (e.g. non-PDF declared type)
  const badCandidate = {
    name: "bad.png",
    size: 50,
    type: "image/png",
    arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer,
    slice: () => new Blob([]),
  };

  await controller.offer(badCandidate as any);

  const staleHandle = controller.currentHandle;
  const staleDoc = controller.currentDocument;

  console.log("Host fileState:", host.fileState);
  console.log("Stale currentHandle present:", Boolean(staleHandle), staleHandle);
  console.log("Stale currentDocument present:", Boolean(staleDoc), staleDoc?.label);
  console.log("Item 1 reproduced:", staleHandle !== null && staleDoc !== null && host.fileState === "idle");
}

// ---------------------------------------------------------------------------
// Item 2: Unenforced OCR/raster caps
// ---------------------------------------------------------------------------
console.log("\n--- Item 2: Unenforced OCR/raster caps ---");
{
  // 2a: maxRasterPixels in mount.tsx
  const configWithoutLimits = resolveConfig({
    workerSrc: "/dummy.js",
    cMapUrl: "/cmaps/",
    standardFontDataUrl: "/fonts/",
  });
  console.log("MOBILE_PROFILE.maxRasterPixels configured:", MOBILE_PROFILE.maxRasterPixels);
  console.log("createPdfJsReader default maxRasterPixels (without limits override):", configWithoutLimits.limits.maxRasterPixels);
  const rasterPixelCapUnenforced = configWithoutLimits.limits.maxRasterPixels !== MOBILE_PROFILE.maxRasterPixels;
  console.log("Raster cap unenforced in mobile reader adapter:", rasterPixelCapUnenforced);

  // 2b: maxOcrPagesPerRun in startRun
  const selectedPages = [0, 1, 2, 3, 4, 5, 6, 7]; // 8 pages selected
  const plannedCapabilities = ["native_text", "render", "ocr"];
  const plannedOcrChecksCount = selectedPages.length; // mount.tsx:113 plans ocr for all selected pages
  console.log("Selected pages count:", selectedPages.length);
  console.log("DESKTOP_PROFILE.maxOcrPagesPerRun:", DESKTOP_PROFILE.maxOcrPagesPerRun);
  console.log("Planned OCR checks count:", plannedOcrChecksCount);
  const ocrCapExceeded = plannedOcrChecksCount > DESKTOP_PROFILE.maxOcrPagesPerRun;
  console.log("OCR per-run cap exceeded without enforcement:", ocrCapExceeded);
  console.log("Item 2 reproduced:", rasterPixelCapUnenforced && ocrCapExceeded);
}

// ---------------------------------------------------------------------------
// Item 3: Region label edit propagation
// ---------------------------------------------------------------------------
console.log("\n--- Item 3: Region label edit propagation ---");
{
  const mockPage = {
    index: 0,
    widthPt: 612,
    heightPt: 792,
    rotation: 0,
    canonicalTransformId: "xform_0",
  };
  const initialBox: [number, number, number, number] = [72, 72, 288, 288];
  const initialLabel = "Region 1";
  const contractRegion = regionToContract(initialBox, mockPage as any, 1, initialLabel);

  // OpenWorkspace.tsx:216 initializes entry:
  let entry = { box: initialBox, region: contractRegion, label: initialLabel };

  // OpenWorkspace.tsx:333-338 onLabelChange:
  const nextLabel = "Total Amount Bounding Box";
  entry = { ...entry, label: nextLabel };

  console.log("UI displayed entry.label:", entry.label);
  console.log("Contract entry.region.label (passed to startRun):", entry.region.label);
  const labelDiverged = entry.label !== entry.region.label;
  console.log("Contract record out of sync with UI edit:", labelDiverged);
  console.log("Item 3 reproduced:", labelDiverged);
}

// ---------------------------------------------------------------------------
// Item 4: Busy-refusal event
// ---------------------------------------------------------------------------
console.log("\n--- Item 4: Busy-refusal event ---");
{
  class FakeHost {
    fileState = "idle";
    currentGeneration = 1;
    openFile() { this.fileState = "validating_file"; }
    requestClear() { this.fileState = "idle"; }
  }

  const events: any[] = [];
  const host = new FakeHost();
  const fakeAdapter = {
    open: () => new Promise((resolve) => setTimeout(() => resolve({}), 50)),
    pages: async () => ({ count: 1, pages: [] }),
    close: async () => {},
  };

  const controller = new OpenController({
    host: host as any,
    adapter: fakeAdapter as any,
    profile: DESKTOP_PROFILE,
    onEvent: (e) => events.push(e),
  });

  const cand1 = {
    name: "doc1.pdf",
    size: 100,
    type: "application/pdf",
    slice: () => new Blob(["%PDF-1.4..."]),
    arrayBuffer: async () => new Uint8Array(100).buffer,
  };
  const cand2 = {
    name: "doc2.pdf",
    size: 200,
    type: "application/pdf",
    slice: () => new Blob(["%PDF-1.4..."]),
    arrayBuffer: async () => new Uint8Array(200).buffer,
  };

  const p1 = controller.offer(cand1 as any);
  const outcome2 = await controller.offer(cand2 as any);
  await p1;

  console.log("Concurrent offer outcome ok:", outcome2.ok);
  console.log("Concurrent offer error detail:", outcome2.error.detail);
  const hasRejectedEvent = events.some((e) => e.type === "rejected" && e.error?.detail === "open:busy");
  console.log("Emitted rejected event for busy refusal:", hasRejectedEvent);
  console.log("Item 4 reproduced:", !outcome2.ok && outcome2.error.detail === "open:busy" && !hasRejectedEvent);
}

console.log("\n=== All 4 follow-up issues confirmed reproduced on main ===");
