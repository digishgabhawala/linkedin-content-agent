// The AI Bharatiyaa family mark, the same as Task Queue's suite bar: links
// home (aibharatiya.com/). Brand colour from the shared tokens (brand-600).
export function SuiteBrand() {
  return (
    <a href="/" aria-label="AI Bharatiyaa home"
      className="inline-flex items-center gap-2 font-semibold text-gray-900 hover:text-[#4946c7]">
      <span aria-hidden="true"
        className="grid h-7 w-7 place-items-center rounded bg-[#4946c7] font-mono text-xs text-white">
        ai
      </span>
      <span translate="no">AI Bharatiyaa</span>
    </a>
  )
}
