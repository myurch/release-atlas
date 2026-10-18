export type SourceDraft = {
  title: string;
  version: string;
  url: string;
  license: string;
  text: string;
};

export type ReadmePreview = {
  revision: number;
  repository: string;
  commit: string;
  path: string;
  source: SourceDraft;
};

export const emptySourceDraft = (): SourceDraft => ({
  title: "",
  version: "",
  url: "",
  license: "",
  text: "",
});

export function readmeFailureMessage(reason: unknown): string {
  const error =
    reason && typeof reason === "object" ? (reason as Error) : new Error("");
  if (error.name === "AbortError")
    return "The README request took too long. Try again or paste the README manually. Your draft is unchanged.";
  if (error.name === "TypeError")
    return "Could not reach the Atlas service. Check that the server is running and try again. Your draft is unchanged.";
  return (
    (typeof error.message === "string" && error.message) ||
    "Could not fetch the README. Try again or paste the text manually. Your draft is unchanged."
  );
}

export function validateReadmePreview(
  value: unknown,
  revision: number,
): ReadmePreview {
  const row = value as ReadmePreview;
  const validText = (text: unknown, max: number): text is string =>
    typeof text === "string" &&
    Array.from(text).length <= max &&
    !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(text) &&
    new TextDecoder().decode(new TextEncoder().encode(text)) === text;
  if (
    !row ||
    row.revision !== revision ||
    !validText(row.repository, 160) ||
    !/^[A-Za-z0-9_-]+\/[A-Za-z0-9_.-]+$/.test(row.repository) ||
    !validText(row.commit, 64) ||
    !/^[a-f0-9]{40}(?:[a-f0-9]{24})?$/.test(row.commit) ||
    !validText(row.path, 500) ||
    !row.path ||
    row.path.split("/").some((part) => ["", ".", ".."].includes(part)) ||
    !row.source ||
    !validText(row.source.title, 160) ||
    !row.source.title.trim() ||
    !validText(row.source.version, 80) ||
    row.source.version !== "commit:" + row.commit ||
    !validText(row.source.text, 12000) ||
    !row.source.text.trim() ||
    !validText(row.source.license, 300) ||
    !validText(row.source.url, 1000) ||
    !row.source.url.startsWith(
      `https://github.com/${row.repository}/blob/${row.commit}/`,
    )
  )
    throw new Error(
      "The fetched README could not be verified. Your draft is unchanged; try again or paste the text manually.",
    );
  return row;
}

export function applyReadmeDraft(
  draft: SourceDraft,
  preview: ReadmePreview,
): SourceDraft {
  return {
    ...draft,
    title: draft.title.trim() ? draft.title : preview.source.title,
    version: draft.version.trim() ? draft.version : preview.source.version,
    text: preview.source.text,
    url: preview.source.url,
  };
}
