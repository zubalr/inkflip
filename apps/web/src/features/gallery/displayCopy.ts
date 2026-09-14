/**
 * Everyday titles and one-line descriptions for the public example cards.
 *
 * Presentation overlay only. Sealed manifests and `/examples/index.json`
 * keep their recorded fixture wording; this map is what Home/gallery show.
 */

export interface ExampleDisplayCopy {
  readonly title: string;
  readonly description: string;
}

export const EXAMPLE_DISPLAY_COPY: Record<string, ExampleDisplayCopy> = {
  amount: {
    title: "An amount changes during extraction",
    description: "The page shows $100. The extracted text reads $1,000.",
  },
  covered: {
    title: "Text covered by a white box",
    description: "A white rectangle covers the amount on the page. The text layer still carries it.",
  },
  scan: {
    title: "A scan with a hidden text layer",
    description: "A searchable scan can agree with OCR, or hide a mismatched text layer.",
  },
  geometry: {
    title: "The same page, rotated",
    description: "The same ink at 90 degrees. Readers have to reconcile the page geometry.",
  },
  "reading-order": {
    title: "Columns read in a different order",
    description: "Two columns emit right then left. The words are the same; the stream order is not.",
  },
  duplicates: {
    title: "Repeated amounts at different positions",
    description: "Four identical $100 amounts stay separate. Matching the string does not collapse them.",
  },
};

export function exampleDisplayCopy(
  exampleId: string,
  fallbackTitle: string,
  fallbackDescription: string,
): ExampleDisplayCopy {
  return (
    EXAMPLE_DISPLAY_COPY[exampleId] ?? {
      title: fallbackTitle,
      description: fallbackDescription,
    }
  );
}
