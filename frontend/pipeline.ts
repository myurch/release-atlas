import { Claim, EntityMention, Workspace } from "./types";

export type PassageFilters = {
  source: string;
  section: string;
  purpose: string;
  entity: string;
  topic: number | null;
};
export const emptyPassageFilters = (): PassageFilters => ({
  source: "",
  section: "",
  purpose: "",
  entity: "",
  topic: null,
});
export const entityKey = (mention: EntityMention) =>
  `${mention.kind}:${mention.normalized}`;
export const sectionKey = (claim: Claim) =>
  JSON.stringify(claim.document?.headings || []);
export function matchesPassage(claim: Claim, filters: PassageFilters): boolean {
  return (
    (!filters.source || claim.source_id === filters.source) &&
    (!filters.section || sectionKey(claim) === filters.section) &&
    (!filters.purpose || claim.document?.purpose === filters.purpose) &&
    (!filters.entity ||
      !!claim.document?.mentions.some(
        (m) => entityKey(m) === filters.entity,
      )) &&
    (filters.topic === null || claim.topic === filters.topic)
  );
}
export function technicalInventory(workspace: Workspace) {
  const rows = new Map<
    string,
    {
      key: string;
      name: string;
      kind: string;
      mentions: number;
      passageIds: Set<string>;
      sourceIds: Set<string>;
      rules: Set<string>;
    }
  >();
  for (const claim of workspace.claims)
    for (const mention of claim.document?.mentions || []) {
      const key = entityKey(mention);
      const row = rows.get(key) || {
        key,
        name: mention.name,
        kind: mention.kind,
        mentions: 0,
        passageIds: new Set<string>(),
        sourceIds: new Set<string>(),
        rules: new Set<string>(),
      };
      row.mentions++;
      row.passageIds.add(claim.id);
      row.sourceIds.add(claim.source_id);
      row.rules.add(mention.rule);
      rows.set(key, row);
    }
  return [...rows.values()].sort(
    (a, b) =>
      b.passageIds.size - a.passageIds.size || a.name.localeCompare(b.name),
  );
}
