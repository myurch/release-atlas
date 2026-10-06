import { Workspace } from "./types";

export type TutorialStep = {
  title: string;
  goal: string;
  explanation: string;
  takeaway: string;
  how?: { concept: string; tools: string; explanation: string };
  tab: "Overview" | "Sources" | "Evidence" | "Graph" | "Questions" | "Activity";
  target: string;
  click?: boolean;
  after?: string;
  action: string;
};
export const REVIEW_NOTE =
  "Checkout service uses retry_limit. The two version 2.0 sources disagree. Confirm the supported setting and test retry behavior before upgrading.";
export const tutorialSteps: TutorialStep[] = [
  {
    title: "Can our application move to Harbor 2.0?",
    goal: "Learn to make an upgrade decision with evidence.",
    explanation:
      "You maintain an application using Harbor, a fictional software library. An upgrade may change settings your application relies on. We will inspect the documents, find a relevant conflict and record what still needs checking.",
    takeaway:
      "Follow the cursor with Next. Back repeats an earlier step. Exit returns to your work, including draft inputs. All tutorial changes are temporary.",
    how: {
      concept: "Interactive application",
      tools: "React · TypeScript",
      explanation:
        "React builds the screens from reusable components. TypeScript checks their data shapes during development. The tutorial operates a separate example view so you can learn the same controls without changing your saved review.",
    },
    tab: "Overview",
    target: ".stats",
    action: "Look at the review overview",
  },
  {
    title: "1. Gather the original documents",
    goal: "Know where a finding came from.",
    explanation:
      "A source is saved text, such as release notes or a configuration guide, labeled with its version. Sources has both the documents and forms for adding your own text or a public GitHub release feed. This example already has three documents.",
    takeaway:
      "Keep the version and permission to use the text with each source. A saved snapshot does not update when the original website changes.",
    how: {
      concept: "API and data-feed integration",
      tools: "Python · FastAPI · HTTPX · GitHub REST API",
      explanation:
        "An API lets programs exchange structured data. In the live workspace, FastAPI handles requests and HTTPX fetches up to three public GitHub releases as JSON. Each release becomes a versioned source you can review. The tutorial uses prepared documents.",
    },
    tab: "Overview",
    target: '[data-tour="nav-Sources"]',
    click: true,
    after: ".source-list",
    action: "Open Sources",
  },
  {
    title: "Read a source before trusting a summary",
    goal: "Check the exact wording and version.",
    explanation:
      "The Harbor 2.0 release notes say retry_limit was removed and retry_policy replaces it. These are names of settings. Later we will compare this passage with another document for the same version.",
    takeaway:
      "The source text is the evidence. A generated label or answer is only a way to help you find it.",
    how: {
      concept: "Source provenance and integrity",
      tools: "Python hashlib · SHA-256",
      explanation:
        "Provenance means keeping the origin and version of evidence. SHA-256 gives each saved text a fingerprint, helping detect changes on import. Claims also retain exact quote positions. A matching fingerprint does not establish that a document is correct.",
    },
    tab: "Sources",
    target: ".source-item",
    click: true,
    after: ".source-text",
    action: "Open the Harbor 2.0 release notes",
  },
  {
    title: "2. Tell Atlas what your application uses",
    goal: "Connect general changes to your own application.",
    explanation:
      "The usage profile pairs a component, a part of your application, with an entity, a named API or setting. Here, Checkout service uses retry_limit. The form uses one component | setting pair per line.",
    takeaway:
      "You supply this profile. Atlas does not scan your code, so a match means potentially relevant, not confirmed impact.",
    how: {
      concept: "Technical entity extraction",
      tools: "Python · Regular expressions",
      explanation:
        "Entity extraction finds named things in text. This implementation uses text patterns to identify APIs and settings in backticks, snake_case or camelCase, then matches them to your usage profile. It does not inspect your application code.",
    },
    tab: "Overview",
    target: '[data-tour="edit-usage"]',
    click: true,
    after: '[data-tour="usage-editor"]',
    action: "Open the usage profile editor",
  },
  {
    title: "3. Turn documents into evidence cards",
    goal: "Find changes worth reviewing.",
    explanation:
      "Analyze sources extracts cited passages called claims, suggests change categories, groups related words into topics and links named settings. The cards count findings, usage matches, conflict candidates and recorded reviews.",
    takeaway:
      "This demonstration replays prepared analysis. In your workspace, Analyze sources processes your current documents and usage profile. Reanalyze after either changes.",
    how: {
      concept: "NLP pipelines and topic modeling",
      tools: "Python · scikit-learn · NMF",
      explanation:
        "Natural language processing (NLP) turns document text into analyzable features. This pipeline extracts passages and identifiers, suggests categories and builds links. Non-negative matrix factorization (NMF) groups passages by shared word patterns, helping you find related changes. Topic groups are not risk ratings.",
    },
    tab: "Overview",
    target: '[data-tour="analyze"]',
    click: true,
    after: ".stats",
    action: "Show the prepared analysis results",
  },
  {
    title: "4. Investigate what affects you",
    goal: "Open a finding linked to Checkout service.",
    explanation:
      "This evidence card preserves the exact quote and links back to its source. Breaking means an existing use may stop working. Usage match means retry_limit appears in our declared profile. Neither label proves an upgrade is unsafe.",
    takeaway:
      "The conflict flag asks you to compare documents. Both passages concern version 2.0, so this is more than an ordinary difference between old and new releases.",
    how: {
      concept: "Embedding-based text classification",
      tools: "scikit-learn · TF-IDF · Truncated SVD · Logistic regression",
      explanation:
        "TF-IDF gives distinctive words more weight. Truncated SVD compresses those features into statistical embeddings, which are number vectors representing text. A trained logistic regression model suggests the change category. These are statistical text models; the displayed score is not a probability of upgrade failure.",
    },
    tab: "Overview",
    target: ".attention-row",
    click: true,
    after: ".claim-detail blockquote",
    action: "Open the retry_limit finding",
  },
  {
    title: "Read both sides of the conflict",
    goal: "Avoid deciding from one passage alone.",
    explanation:
      "The configuration reference says retry_limit remains supported in 2.0. That competes with the release note saying it was removed. The link takes us directly to the other evidence card, keeping its source attached.",
    takeaway:
      "This is a conflict candidate, not proof that one document is wrong. Resolve it with the maintainer or a behavior test before relying on the setting.",
    how: {
      concept: "Rule-based conflict detection",
      tools: "Python · Regular expressions",
      explanation:
        "The detector compares removal and support wording for the same identifier and exact version. This explicit rule flags passages for comparison. It is not an ML verdict: wording variations, complex negation or version ranges can escape the rule.",
    },
    tab: "Evidence",
    target: '[data-tour="other-claim"]',
    click: true,
    after: ".claim-detail blockquote",
    action: "Read the other claim",
  },
  {
    title: "5. Write a useful review decision",
    goal: "Record the uncertainty and the next concrete check.",
    explanation:
      "Needs investigation is the honest choice here. Applicable means the finding affects your usage; Not applicable means you checked that it does not. Neither decision is a blanket approval for the entire upgrade.",
    takeaway:
      "The example note names the affected component, explains the disagreement and calls for a supported-setting check and a retry behavior test.",
    how: {
      concept: "Human-in-the-loop review",
      tools: "React · TypeScript · Python",
      explanation:
        "Human-in-the-loop means a person checks machine suggestions before acting on them. Your decision and explanation are stored separately from the suggested category and usage match. Saving a review records your judgment; it does not retrain the classifier.",
    },
    tab: "Evidence",
    target: ".review-form textarea",
    action: "Read the example decision and note",
  },
  {
    title: "Save the review so the team can act",
    goal: "Leave a visible decision with a reason.",
    explanation:
      "Save review records the decision, note, reviewer name and time. Other connected reviewers see saved changes. Atlas rejects an outdated save if the shared workspace changed while someone was writing.",
    takeaway:
      "We have saved a temporary tutorial review. Your actual workspace and its history have not changed.",
    how: {
      concept: "Live multiuser collaboration",
      tools: "React · TypeScript · FastAPI · SSE · SQLite",
      explanation:
        "Server-Sent Events (SSE) notify connected browsers when a revision changes. SQLite saves each change atomically, meaning all of it succeeds together. An expected-revision check rejects outdated writes so one reviewer cannot silently overwrite another. Here, the save stays inside the tutorial.",
    },
    tab: "Evidence",
    target: '[data-tour="save-review"]',
    click: true,
    after: '[data-tour="saved-review"]',
    action: "Save the example review",
  },
  {
    title: "6. Explore how the evidence connects",
    goal: "Follow a component to the settings and claims around it.",
    explanation:
      "A graph is a map of items, called nodes, connected by relationships, called links. Checkout service connects to retry_limit; that setting connects to cited claims. The selector and the list let you move around the map.",
    takeaway:
      "Connections show why evidence was found. They do not prove causation. The list gives a readable alternative to the diagram.",
    how: {
      concept: "Knowledge graphs and network analysis",
      tools: "Python · NetworkX",
      explanation:
        "NetworkX builds a knowledge graph linking sources, claims, settings and application components. Typed relationships describe how items connect; a node’s degree counts its links. Inspecting neighbors and paths lets you trace a component to the evidence behind a finding.",
    },
    tab: "Overview",
    target: '[data-tour="nav-Graph"]',
    click: true,
    after: ".graph-panel",
    action: "Open the evidence graph",
  },
  {
    title: "7. Ask a focused question",
    goal: "Find evidence for a specific part of your application.",
    explanation:
      "Ask what affects Checkout service. Keyword search matches words; text embeddings look for similar meaning; graph plus text also follows your declared connections. An optional model can draft an answer from retrieved passages.",
    takeaway:
      "A citation is a link to evidence, not a guarantee the answer is correct. This tutorial uses a prepared, cited example and does not call a model.",
    how: {
      concept: "Text retrieval and graph-assisted search",
      tools: "scikit-learn · LSA · NetworkX",
      explanation:
        "Retrieval selects passages to inspect. Keyword mode compares weighted words. Default vector mode uses latent semantic analysis (LSA), a statistical text embedding method. Graph mode also follows relationships within three links, bringing in relevant claims even when the question uses a component name absent from the passage.",
    },
    tab: "Overview",
    target: '[data-tour="nav-Questions"]',
    click: true,
    after: '[data-tour="question-form"]',
    action: "Open Questions",
  },
  {
    title: "Inspect the answer and its citations",
    goal: "Check whether the answer actually supports your decision.",
    explanation:
      "The example answer brings together the two retry_limit passages and preserves the uncertainty. The numbered citations open the original evidence cards so you can check the answer yourself.",
    takeaway:
      "Do not treat a fluent answer as permission to upgrade. Our next action is still to resolve the documentation conflict and test the behavior.",
    how: {
      concept: "RAG and graph-assisted RAG",
      tools: "Ollama · OpenAI-compatible APIs · NetworkX",
      explanation:
        "Retrieval-augmented generation (RAG) supplies retrieved evidence to a language model before it drafts an answer. Graph-assisted RAG (GraphRAG) also uses relationships to select that evidence. In your workspace, generation is optional through Ollama or an OpenAI-compatible API. This tutorial answer is prepared, not generated live.",
    },
    tab: "Questions",
    target: '[data-tour="ask"]',
    click: true,
    after: ".answer",
    action: "Show the prepared evidence answer",
  },
  {
    title: "Follow a citation back to the evidence",
    goal: "Verify a statement rather than taking it on trust.",
    explanation:
      "Clicking citation 1 returns to the exact quoted passage, its version and its source. This is the same evidence card we reviewed. You can always return to Sources for the surrounding document.",
    takeaway:
      "A useful evidence trail goes from question to answer to claim to source. Keep that trail intact when sharing a review.",
    how: {
      concept: "Grounding and citation validation",
      tools: "Python · Pydantic · TypeScript",
      explanation:
        "Grounding ties an answer to supplied evidence. Pydantic checks the model response structure, and Python rejects citation IDs outside the retrieved set. Snapshot validation checks that quoted text matches its source positions. These checks preserve the evidence trail; they do not prove the answer is true.",
    },
    tab: "Questions",
    target: ".citation",
    click: true,
    after: ".claim-detail blockquote",
    action: "Open citation 1",
  },
  {
    title: "8. Check the history and share a snapshot",
    goal: "Hand another reviewer the evidence and recorded decisions.",
    explanation:
      "Activity records saved changes. Export snapshot downloads the current review as a JSON file containing source text, findings and notes. Another reviewer can use Import to open it. The snapshot does not include access codes or model credentials.",
    takeaway:
      "Check source permissions and review names before sharing. Workspaces lets you create an empty review or switch to an earlier one without deleting it.",
    how: {
      concept: "Structured data and audit history",
      tools: "JSON · SQLite · Pydantic",
      explanation:
        "JSON stores the review in a structured, portable format. Pydantic validates imported data before the service saves it. SQLite retains each workspace’s review history, while revision checks protect shared edits. This history records review actions, not source-code commits.",
    },
    tab: "Overview",
    target: '[data-tour="nav-Activity"]',
    click: true,
    after: '[data-tour="export"]',
    action: "Open Activity, then locate Export snapshot",
  },
  {
    title: "Your first review has a clear next action",
    goal: "Decide what must happen before this upgrade proceeds.",
    explanation:
      "For this example, hold the Checkout change until the retry_limit conflict is resolved and retry behavior is tested. We traced the documents, matched our usage, compared both claims and recorded a reasoned review. The remaining findings still need review.",
    takeaway:
      "For your own upgrade: Workspaces → New empty workspace, add versioned sources, edit the usage profile, analyze, verify findings and save reviews. Finish returns to your work. You can restart this tutorial anytime.",
    how: {
      concept: "Evaluation against a baseline",
      tools: "pytest · scikit-learn · Node.js tests",
      explanation:
        "Outside the tutorial, evaluation compares classification with a simple keyword baseline and measures retrieval of relevant evidence. Tests also check citation integrity and outdated writes. These checks make behavior inspectable; results on a small synthetic dataset do not establish production accuracy.",
    },
    tab: "Overview",
    target: ".stats",
    action: "Review what you accomplished",
  },
];

export function emptyWorkspace(title = "Untitled review"): Workspace {
  return {
    schema_version: 1,
    revision: 0,
    title,
    sources: [],
    usage: [],
    claims: [],
    topics: [],
    graph: { nodes: [], edges: [] },
    analysis: null,
    answers: [],
    audit: [],
  };
}
export function tutorialClaim(fixture: Workspace) {
  const claim = fixture.claims.find(
    (c) => c.conflicts.length && c.entities.includes("retry_limit"),
  );
  if (!claim)
    throw new Error("Tutorial fixture is missing its cited conflict.");
  return claim;
}
export function addTutorialReview(state: Workspace): Workspace {
  const next = structuredClone(state);
  const claim = tutorialClaim(next);
  next.revision += 1;
  claim.review = {
    status: "needs-investigation",
    note: REVIEW_NOTE,
    by: "Tutorial reviewer",
    at: "2026-10-06T12:00:00Z",
  };
  next.audit.push({
    at: claim.review.at,
    by: claim.review.by,
    action: "Reviewed retry_limit: needs investigation (tutorial)",
    revision: next.revision,
  });
  return next;
}
export function addTutorialAnswer(state: Workspace): Workspace {
  const next = structuredClone(state);
  const claim = tutorialClaim(next);
  next.revision += 1;
  next.answers = [
    {
      id: "a-tutorial",
      question: "What affects Checkout service?",
      answer:
        "Checkout service declares use of retry_limit. The Harbor 2.0 release notes say the setting was removed, while the 2.0 configuration reference says it remains supported. Confirm the supported configuration and test retry behavior before upgrading.",
      citations: [claim.id, ...claim.conflicts],
      uncertainty:
        "Prepared tutorial answer. The competing guidance remains unresolved; other upgrade findings still need review.",
      method: "Prepared tutorial example with source citations",
      at: "2026-10-06T12:01:00Z",
    },
  ];
  next.audit.push({
    at: next.answers[0].at,
    by: "Tutorial reviewer",
    action: "Opened prepared evidence answer (tutorial)",
    revision: next.revision,
  });
  return next;
}
export function tutorialWorkspace(fixture: Workspace, step: number): Workspace {
  let state = structuredClone(fixture);
  state.audit = [];
  state.answers = [];
  state.claims.forEach((c) => (c.review = null));
  if (step > 8) state = addTutorialReview(state);
  if (step > 11) state = addTutorialAnswer(state);
  return state;
}
