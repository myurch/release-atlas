import { Workspace } from "./types";

export type SourceActionItem = {
  source_id: string;
  source: Omit<Workspace["sources"][number], "id" | "sha256">;
};
export type SourceAction = SourceActionItem & {
  action: "add_source" | "delete_source";
  items?: SourceActionItem[];
  match_text?: string;
  removed_findings: number;
  removed_answers: number;
  token: string;
  revision: number;
};

export const sourceActionItems = (action: SourceAction): SourceActionItem[] =>
  action.items ?? [{ source_id: action.source_id, source: action.source }];

export const sourceActionLabel = (action: SourceAction): string => {
  const count = sourceActionItems(action).length;
  return `${action.action === "add_source" ? "Add" : "Delete"} ${count} ${count === 1 ? "source" : "sources"}`;
};

const sameSource = (
  a: SourceActionItem["source"],
  b: SourceActionItem["source"],
) =>
  ["title", "version", "text", "url", "license"].every(
    (key) => a[key as keyof typeof a] === b[key as keyof typeof b],
  );

export function validatedSourceAction(
  value: unknown,
  workspace: Workspace,
): SourceAction | undefined {
  if (value == null) return undefined;
  const action = value as SourceAction;
  if (
    !["add_source", "delete_source"].includes(action.action) ||
    action.revision !== workspace.revision ||
    typeof action.token !== "string" ||
    !/^[A-Za-z0-9_-]{32,100}$/.test(action.token) ||
    typeof action.source_id !== "string" ||
    !/^s-[a-f0-9]{20}$/.test(action.source_id) ||
    !action.source ||
    !["title", "version", "text", "url", "license"].every(
      (key) =>
        typeof action.source[key as keyof typeof action.source] === "string",
    ) ||
    ![action.removed_findings, action.removed_answers].every(
      (count) => Number.isInteger(count) && count >= 0,
    ) ||
    (action.action === "delete_source" &&
      !workspace.sources.some(
        (source) =>
          source.id === action.source_id &&
          source.title === action.source.title &&
          source.version === action.source.version &&
          source.text === action.source.text &&
          source.url === action.source.url &&
          source.license === action.source.license,
      ))
  )
    throw new Error(
      "The source action could not be verified. Ask Atlas again.",
    );
  const items = sourceActionItems(action);
  if (
    !Array.isArray(items) ||
    items.length < 1 ||
    items.length > 30 ||
    new Set(items.map((item) => item?.source_id)).size !== items.length ||
    !items[0] ||
    items[0].source_id !== action.source_id ||
    !items[0].source ||
    !sameSource(items[0].source, action.source) ||
    (action.match_text !== undefined &&
      (typeof action.match_text !== "string" ||
        Array.from(action.match_text).length > 200)) ||
    items.some(
      (item) =>
        !item ||
        typeof item.source_id !== "string" ||
        !/^s-[a-f0-9]{20}$/.test(item.source_id) ||
        !item.source ||
        !["title", "version", "text", "url", "license"].every(
          (key) =>
            typeof item.source[key as keyof typeof item.source] === "string",
        ) ||
        (action.action === "delete_source" &&
          !workspace.sources.some(
            (source) =>
              source.id === item.source_id && sameSource(source, item.source),
          )),
    )
  )
    throw new Error("The source batch could not be verified. Ask Atlas again.");
  return action;
}
