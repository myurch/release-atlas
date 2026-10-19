import { RetrievalReport } from "./retrieval";
export type QuestionGraph = {
  requestId: number;
  revision: number;
  scopeKey: string;
  question: string;
  phase: "loading" | "ready" | "error";
  report?: RetrievalReport;
};
export type QuestionGraphEvent = {
  requestId: number;
  revision: number;
  question: string;
  phase: "loading" | "ready" | "error";
  report?: RetrievalReport;
} | null;
export function advanceQuestionGraph(
  previous: QuestionGraph | null,
  event: QuestionGraphEvent,
  scope: { key: string; revision: number; page: string; enabled: boolean },
): QuestionGraph | null {
  if (!event) return null;
  if (!scope.enabled || event.revision !== scope.revision) return previous;
  if (event.phase === "loading")
    return scope.page === "Graph"
      ? { ...event, scopeKey: scope.key }
      : previous;
  // An existing Graph request can finish while the user reads another page.
  // Visibility remains page-scoped; retention and progress do not.

  if (
    !previous ||
    previous.requestId !== event.requestId ||
    previous.scopeKey !== scope.key ||
    previous.revision !== event.revision
  )
    return previous;
  return {
    ...previous,
    phase: event.phase,
    report: event.report ?? previous.report,
  };
}

export function visibleQuestionGraph(
  graph: QuestionGraph | null,
  scope: { key: string; revision: number; page: string; enabled: boolean },
): QuestionGraph | null {
  return scope.enabled &&
    scope.page === "Graph" &&
    graph?.scopeKey === scope.key &&
    graph.revision === scope.revision
    ? graph
    : null;
}
