import { Workspace } from "./types";
import { help } from "./help-content";

export function guideReply(
  page: string,
  workspace: Workspace,
  question: string,
  readOnly = false,
): string {
  const query = question.toLowerCase();
  if (readOnly) {
    if (
      /next|start|workflow|do i do|this page|explain/.test(query) &&
      !/graph|retriev|source|conflict/.test(query)
    ) {
      const intro = help[page] || help.Overview;
      return `${intro.title}\n\n${intro.what}\n\nIn this viewer, open Evidence to compare passages, Sources to read their original text, or Graph to follow connections. Questions shows saved answers when included in the review. Try Beginner tutorial to practice the workflow. Analysis, saving shared decisions and live AI answers require the full application.`;
    }
    if (
      /upload|add.*source|analy|save|review|decision|model|llm|generat|workspace|switch/.test(
        query,
      )
    ) {
      return "This viewer lets you explore prepared or imported reviews. It cannot analyze new sources, save shared decisions or generate AI answers.\n\nUse Import for an exported review, explore the evidence and graph, or start Beginner tutorial to see the complete workflow with prepared examples. The full application supports new analysis, collaboration and an optional model connection.";
    }
  }
  const topics: [RegExp, string][] = [
    [/export|share|download/, "export"],
    [/import|upload|pdf|github|document/, "Sources"],
    [/conflict|contradict|disagree/, "conflicts"],
    [/classif|category|score|risk/, "category"],
    [/topic|nmf/, "topics"],
    [/usage|component|setting|api name/, "usage"],
    [/graph|network|relationship/, "Graph"],
    [/embedding|retriev|vector|similarity/, "retrieval"],
    [/citation|source of|quote/, "citation"],
    [/review|decision|note/, "saveReview"],
    [/model|llm|rag|generat/, "generation"],
    [/theme|dark|light/, "theme"],
    [/workspace|example|switch/, "workspaces"],
    [/analy/, "analysis"],
  ];
  const matched = topics.find(([pattern]) => pattern.test(query));
  if (matched) {
    const item = help[matched[1]];
    return `${item.title}\n\n${item.what}\n\n${item.why}`;
  }
  if (/next|start|workflow|do i do|help|this page|explain/.test(query)) {
    const intro = help[page] || help.Overview;
    const next = !workspace.sources.length
      ? "1. Open Sources and add versioned release notes or reference text.\n2. In Overview, describe the settings or APIs your application uses.\n3. Choose Analyze sources, then inspect the evidence."
      : !workspace.analysis
        ? "1. Check that source versions and application usage are correct.\n2. Choose Analyze sources.\n3. Open Evidence and review relevant findings and possible conflicts."
        : "1. Open Evidence and focus on usage matches or conflicting claims.\n2. Read the original passages and save a decision with your reasoning.\n3. Use Graph or Questions to explore connections, then export the review when ready.";
    return `${intro.title}\n\n${intro.what}\n\n${next}`;
  }
  if (readOnly)
    return "App guide provides built-in explanations, not live AI answers. Ask how the graph, sources, conflicts or retrieval work, or try Beginner tutorial for a walkthrough.";
  return "The app guide can explain the review workflow and its controls. Try “What should I do next?”, “How does graph retrieval work?” or “How do I add a source?”\n\nFor an open-ended question or an answer about specific evidence, use Model chat in a signed-in live workspace. Guide replies are built-in help, not generated analysis.";
}
