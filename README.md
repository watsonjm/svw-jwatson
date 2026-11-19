# Skills Validation Workshop

Solutions for the L400 Advanced ADK Skills Validation Workshop, built with
[Google ADK](https://adk.dev) 2.x and Gemini on Google Cloud.

| Challenge | Folder |
|---|---|
| 1. Multi-agent workflow | [challenge-1-multi-agent-workflow](challenge-1-multi-agent-workflow) |
| 2. RAG and Google Search | [challenge-2-rag-and-search](challenge-2-rag-and-search) |

## Setup

Requires [uv](https://docs.astral.sh/uv/) and the [gcloud CLI](https://cloud.google.com/sdk/docs/install).

```bash
export PROJECT_ID=your-gcp-project-id

gcloud auth application-default login
gcloud auth application-default set-quota-project $PROJECT_ID
gcloud services enable aiplatform.googleapis.com --project $PROJECT_ID

sed "s/your-gcp-project-id/$PROJECT_ID/" .env.example > .env
uv sync
```

Agents use `MODEL` (`gemini-3.8-flash`) and switch to `FALLBACK_MODEL`
(`gemini-3.5-flash`) when it returns 429 or 5xx (overloaded). 3.8 Flash is only
served from the `global` location, so the code pins both models there.

---

## Challenge 1: Multi-agent workflow

**Product Scout** compares two similar products and names the best one for the
buyer's use case, priorities, and budget. Code: [product_scout/agent.py](challenge-1-multi-agent-workflow/product_scout/agent.py).

```
product_scout (root agent)
├── save_comparison_request   tool: saves products, category, use case, priorities, budget to state
├── product_lookup_agent      sub-agent: identifies products, finds equivalents (Google Search)
├── feature_explainer_agent   sub-agent: explains what a feature means for the user (Google Search)
└── comparison_workflow       ADK 2 workflow:
      1. research_agent_a + research_agent_b, in parallel (Google Search)
      2. comparison_writer: spec table, pros/cons, named winner
      3. verdict_critic ⇄ refiner (both use Google Search) until the critic replies
         APPROVED (max 3 critic passes; every rewrite is re-checked)
      4. ask_if_adequate pauses for the user (RequestInput); route_reply sends "yes" to
         finalize, anything else to apply_feedback (refiner + critic) and asks again
```

| Requirement | How it is met |
|---|---|
| Multi-agent system with suitable output | Root agent plus seven specialists produce a sourced comparison with a verdict. |
| Root agent routes requests and hands off | Product questions go to `product_lookup_agent`, "what does this feature mean?" goes to `feature_explainer_agent`, comparisons go to `comparison_workflow`. |
| Workflow researches, validates, refines | Research both products, write, then critic/refiner loop. The critic checks facts and whether the named winner is really best for this buyer. |
| Data passed via session state | Each agent writes with `output_key` (`research_a`, `research_b`, `draft_comparison`, `critique`, ...) and reads with `{key}` in its instruction. The buyer's request persists across the conversation. |
| Bonus: human input | The workflow pauses with ADK's `RequestInput`. Reply `yes` to accept, or describe a change to refine again. |

### Run locally

```bash
# Test: run the agent as-is
uv run adk web challenge-1-multi-agent-workflow

# Dev: same, but reloads the agent whenever its code changes
uv run adk web --reload_agents challenge-1-multi-agent-workflow
```

Open http://localhost:8000 and select `product_scout`.

### Using it

Describe what you want in plain language. You don't need to know both products:
name one and ask for the closest equivalent from another brand. Mention discounts,
budget, or priorities and the comparison weighs them. For example:

> I want to compare the predator outdoors Matrix 15-384 LRF vs whatever Vortex's
> nearest equivalent is. I get a 10% discount off predator outdoors and 40% off at
> Vortex, unless there is already a sale. I also get 10% off at Cabelas/BassPro,
> which is usually cheaper for Vortex products than Vortex itself.

What happens:

1. The root agent saves your request to state and hands off to
   `product_lookup_agent`, which identifies the Matrix (a thermal monocular with a
   laser rangefinder) and finds Vortex's closest model. Confirm the match.
2. Ask what a spec means at any point, e.g. `what does sensor resolution actually
   affect?` (handoff to `feature_explainer_agent`).
3. Ask for the comparison. The workflow researches both products, uses the best
   price available to you for each, writes a comparison table with one winner, and
   runs the critic/refiner loop.
4. When asked if the comparison is adequate, request a change (e.g. `add a row for
   weight in grams`) or reply `yes` to accept it.

A comparison takes a few minutes because each step runs live Google searches. The
**State** tab in the web UI shows the data each agent wrote (`product_a`,
`category`, `research_a`, `draft_comparison`, `critique`, `final_comparison`, ...).

### Deploy to Agent Runtime

Deploys the agent into your project and prints a Cloud Console link to its
playground, where you can chat with it.

```bash
gcloud services enable aiplatform.googleapis.com cloudresourcemanager.googleapis.com --project $PROJECT_ID

uv run adk deploy agent_engine \
  --project $PROJECT_ID --region us-central1 \
  --display_name "Product Scout" --python_version 3.14 \
  challenge-1-multi-agent-workflow/product_scout
```

The deploy takes several minutes. Open the printed
`https://console.cloud.google.com/vertex-ai/agents/agent-engines/...` link, or find
**Product Scout** under **Agent Platform → Agent Runtime** in the console. To
redeploy over the same instance, add `--agent_engine_id <ID>`. Agent Runtime is
billed while deployed; delete it from the console when done.

### Run in Google Cloud Shell

Open [Cloud Shell](https://shell.cloud.google.com), clone this repo, and follow
Setup (skip the `application-default` steps; Cloud Shell is already
authenticated). Then:

```bash
uv run adk web challenge-1-multi-agent-workflow --port 8080
```

Open it with **Web Preview → Preview on port 8080**.

---

## Challenge 2: RAG and Google Search

**Ember Support** answers questions about Ember Optics, a fictional thermal-optics
company in the fictional town of Emberline, Montana. Product questions are answered
from the company's private documents (RAG); everything else comes from live Google
Search. Code: [ember_support/agent.py](challenge-2-rag-and-search/ember_support/agent.py).
Documents: [ember_docs/](challenge-2-rag-and-search/ember_docs) (manuals, error
codes, firmware notes, accessories; product specs are modeled on real thermal
monoculars, everything else is made up).

```
ember_support (root agent)
├── docs_agent         AgentTool → VertexAiSearchTool over the ember-docs datastore (RAG)
└── web_search_agent   AgentTool → google_search (news, sports, weather, other brands)
```

The specialists are wrapped in `AgentTool` rather than added as `sub_agents`:
`VertexAiSearchTool` must be the only tool on its agent, and a sub-agent also gets
ADK's transfer tool, which makes it hand the question straight back.

Product questions only ever come from the documents; if they don't have the
answer, the agent says so. Questions that need both (e.g. an Ember model versus
another brand) use both sub-agents.

### Create the datastore

**One command:**

```bash
./challenge-2-rag-and-search/create_datastore.sh $PROJECT_ID
```

The project ID can be passed as the argument or set as `PROJECT_ID` in the
environment. The script:

1. enables the Agent Search (Discovery Engine) and Cloud Storage APIs,
2. uploads `ember_docs/` to `gs://<project>-ember-docs` (creating the bucket if needed),
3. creates a datastore with ID `ember-docs` in the `global` location,
4. imports the documents and waits until the import finishes (5-10 minutes,
   printing progress every 15 seconds).

The datastore ID `ember-docs` matches `DATASTORE_ID` in `.env.example`, so no
`.env` change is needed. To use a different ID, run with
`DATASTORE_ID=my-id ./challenge-2-rag-and-search/create_datastore.sh $PROJECT_ID`
and set the same `DATASTORE_ID` in `.env`. A deleted datastore's ID stays reserved
for up to a couple of hours, so use a new ID if you recreate it.

**Or in the console:**

1. Upload the documents: `gcloud storage buckets create gs://$PROJECT_ID-ember-docs --location US`
   then `gcloud storage cp challenge-2-rag-and-search/ember_docs/*.txt gs://$PROJECT_ID-ember-docs/ember_docs/`.
2. Open **AI Applications → Data Stores → Create data store**.
3. Source: **Cloud Storage**. Choose **Unstructured documents (PDF, HTML, TXT and more)**,
   **Folder**, and browse to `$PROJECT_ID-ember-docs/ember_docs`. Click **Continue**.
4. Location: **global**. Name: `ember-docs`. If a **Data store ID** field is shown,
   set it to `ember-docs`. Leave parsing and chunking at their defaults. Click **Create**.
5. Open the datastore and wait for the import on the **Activity** tab to finish.
6. If the datastore ID is not exactly `ember-docs`, copy it from the **Data** page into
   `.env` as `DATASTORE_ID=<id>`.

### Run

```bash
uv run adk web --reload_agents challenge-2-rag-and-search
```

Select `ember_support` and try:

- `My Ember 384 LRF shows E7. How do I fix it?` (documents: boresight steps)
- `Which firmware added Hog Highlight?` (documents: 2.3, June 18, 2026)
- `Can I use an EB-18650 battery in the Ember 256?` (documents: no, built-in battery)
- `Who is playing NFL football tonight?` (Google Search)
- `How does the Ember 384 LRF compare to the Vortex Veil 400?` (both)
