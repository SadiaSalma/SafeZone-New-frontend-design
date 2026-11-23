"use client";
/**
 * Frontend (web) · InlineScript.tsx - a tiny script that runs while the page is still loading,
 * before anything is painted (used to restore the saved colour theme and language,
 * so the page never "flashes" in the wrong colours).
 *
 * This is the pattern from the Next.js 16 guide "Preventing flash before hydration":
 * on the server the tag is real JavaScript; in the browser React sees "text/plain",
 * so it does not warn about rendering a <script>. suppressHydrationWarning accepts the difference.
 */
export function InlineScript({ html }: { html: string }) {
  return (
    <script
      type={typeof window === "undefined" ? "text/javascript" : "text/plain"}
      suppressHydrationWarning
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
