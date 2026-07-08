/**
 * Inline citation marker. Deliberately just a small numbered circle (like
 * a footnote), not literal "S1"/"S2" text -- that reads as an internal
 * debugging label, not something end users should see. Filename and page
 * are still fully available, just moved to the hover tooltip and the
 * Source Viewer that opens on click, so the sentence flow of the answer
 * stays uninterrupted.
 */
export default function CitationChip({ index, citation, onClick }) {
  return (
    <button
      onClick={() => onClick(citation)}
      title={`${citation.filename}${citation.page != null ? ` · p.${citation.page}` : ""}`}
      aria-label={`Source ${index}: ${citation.filename}`}
      className="inline-flex items-center justify-center mx-0.5 h-4 w-4 rounded-full bg-brand-100 text-brand-700 text-[10px] font-semibold leading-none align-super hover:bg-brand-200 transition-colors"
    >
      {index}
    </button>
  );
}
