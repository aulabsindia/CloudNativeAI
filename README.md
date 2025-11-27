# **Cloud Native Hybrid RAG with Multi-Model Consensus & Refinement**

Cloud Native- Hybrid Retrieval Augmented Generation Framework **[CN-HyRAG]** automatically validates and refines AI-generated Kubernetes client-go based code through multi-model consensus and iterative golangci-lint validation—eliminating the manual debugging loop that wastes hours of developer time.

**Terminology:** 
CN‑HyRAG stands for “Cloud Native Hybrid RAG.”

![WhatsApp Image 2025-11-27 at 11 27 28 AM](https://github.com/user-attachments/assets/88dafacd-9453-4e75-9119-25d883a5f1c4)


**Perfect for:** 
- MLOps/AIOps engineers
- Platform teams
- SREs
- Kubernetes developers building client-go utilities and code assistants.

**DEMO :**
See the Refinement Process with CN-HyRAG framework and usage of generated K8s code with the DEMO kit: 
[<a href="https://youtu.be/qv6fUD3ilO8" target="_blank">
  <strong>Click for DEMO video</strong>
</a>]
This evaluation pipeline is designed to demonstrate framework capabilities for cloud-native applications and does not constitute a ranking, endorsement, or recommendation of any model or vendor.

**Try it yourself:**
[<a href="https://github.com/aulabsindia/CloudNativeAI/blob/main/USAGE_GUIDE.md" target="_blank">
  <strong>Jump to Quick Start</strong>
</a>]


The Problem
------------------------
AI code generators and latest state of art LLMs have revolutionized development, but AI-generated Kubernetes client-go code fails validation half of the time due to:
*  Incorrect import paths and package references
* golangci-lint errors (undefined variables, unused imports, logic flaws)
*  Non-idiomatic Go patterns that won't pass code review
*  Single-model bias leading to inconsistent quality
As a result of which developers spend hours debugging AI responses, negating the productivity gains that AI promises.

Existing RAG frameworks focus on retrieval but lack: 
-------------------------------------------------------------------------
- Native code validation integration
- Multi-model consensus mechanisms
- Iterative self-correction capabilities
- Cloud Native domain-specific optimization for Kubernetes client-go

**CN-HyRAG** fills this gap with the first self-healing, multi-model RAG framework purpose-built for Kubernetes code generation.

## Why CN‑HyRAG? 
Unlike single-model code generators that produce inconsistent, error-prone code, CN-HyRAG combines:
- Multi‑model consensus: queries multiple (2+) LLMs in parallel and ranks outputs by code quality, reducing single‑model bias by 50–60%. 
- Self‑healing validation: detects golangci‑lint errors and iteratively refines code until errors are fixed, achieving 95%+ second‑pass success.  
- Hybrid semantic‑syntactic retrieval: combines AST‑based parsing with embedding search to retrieve structurally correct and contextually relevant patterns.  
- Cloud‑native architecture: runs as containerized services (Docker Compose) with Qdrant; deploy anywhere in ~5 minutes.  
- Production‑ready output: generated code passes golangci‑lint and follows Kubernetes client‑go best practices.

See [<a href="https://github.com/aulabsindia/CloudNativeAI/blob/main/KEY_FEATURES.md" target="_blank">
  <strong>KEY_FEATURES.md</strong>
</a>] for additional details.

Known Limitations of CN-HyRAG v1.0
----------------------------------
This initial release focuses on Go code generation for Kubernetes client-go workflows. The following capabilities are planned for future releases:
- **Kubernetes manifests**: Docker Compose provided; full Kubernetes deployment manifests (Deployment, Service, ConfigMap, Secret, PVCs) will be added before conference demo (see <a href="https://github.com/aulabsindia/CloudNativeAI/blob/main/ROADMAP.md" target="_blank">
  <strong>ROADMAP.md</strong>
</a>)
- **Batch query processing**: One query at a time; batch/concurrent query handling not available.

## Tech stack
-------------------------
- LlamaIndex — RAG framework and vector operations.
- Qdrant — High‑performance vector database.
- Tree‑sitter — Multi‑language AST parsing.
- golangci‑lint — Static analysis for Go.
- Flask — REST API framework.
- Azure OpenAI Token — Embeddings and LLM APIs.
- OpenAI Python Client — Compatible API support.

### Infrastructure
--------------------
- Docker — Containerization.
- Docker Compose — Multi‑container orchestration.
- Bash — Validation scripting.
- Python - Runtime(3.12)

### Validation tools
----------------------
- golangci‑lint — Go linter.
- Go toolchain — go.mod, go build.

### COMPATIBILITY
The framework in dockerized form is driven by the environment configuration defined in the `.env` file. All components comprising of model selection, embedding service, vector database, and server parameters are automatically populated from these environment variables at startup. 
This makes the system portable across environments. See [<a href="https://github.com/aulabsindia/CloudNativeAI/blob/main/CONFIGURATION.md" target="_blank">
  <strong>CONFIGURATION.md</strong>
</a>]


**API Quick Start:**
----------------------
Run these [/build, /verbose, /query-multi and /query] endpoints to build the index, inspect status, evaluate model response and generate code. See [<a href="https://github.com/aulabsindia/CloudNativeAI/blob/main/API_ENDPOINTS.md" target="_blank">
  <strong>API_ENDPOINTS.md</strong>
</a>] for detailed reference guide.

**Build Index**

```
curl -s -X POST http://localhost:5001/build \
  -H "Content-Type: application/json" \
  -d '{"directory": "/workspace/feeds"}' | jq

```
**Check status**

```curl -s http://localhost:5001/verbose | jq```

**Generate best reponse:**

```
curl -s -X POST http://localhost:5001/query \
-H "Content-Type: application/json" \
-d '{"query":"Generate a handler to list ingress resources using client-go." }'
```


**Use Cases & Demo Scenarios:**
- Develop [Kubernetes client-go utilities](https://github.com/aulabsindia/k8s-demo-tools).  
  _Demo available at the above link._
- Create a pattern library for logging, telemetry, audits, metrics, comments, and error handling.  
- Use as a code assistant : Apply refinement loops with LLMs to iteratively improve existing Go code against linting standards.  
- Act as a developer onboarding assistant : Generate example code matching your team’s coding standards and project structure.

**How It Works:**
----------------------
The Retrieval-Augmented Generation (RAG) system in the framework supports Golang source code. Golang code bases forming the knowledge base are indexed into a Qdrant vector store through a multi-layered parsing and chunking process handled by the ingestion layer. For each user query, relevant context is retrieved from Qdrant and processed through a multi-model query pipeline, invoking multiple models in parallel. The generated responses then undergoes validation, with static analysis using golangci-lint. Each model is ranked based on lint errors and other quality metrics, followed by an iterative refinement loop to produce the final, error-free response.

**Performance:**
---------------
See [<a href="https://github.com/aulabsindia/CloudNativeAI/blob/main/PERFORMANCE.md" target="_blank"> <strong>PERFORMANCE.md</strong> </a>] for end-to-end timings and quality benchmarks from our latest lab runs.

**Architecture**
---------------------
**Diagram below shows the architecture of Cloud Native Hybrid RAG which its three core components.**
<img width="1142" height="1022" alt="image" src="https://github.com/user-attachments/assets/02e42da8-73ac-4bea-a039-7dc0189f5812" />

A deep dive into the design and architecture can be found in 
<a href="https://github.com/aulabsindia/CloudNativeAI/blob/main/ARCHITECTURE.md" target="_blank">
  <strong>ARCHITECTURE.md</strong>
</a>

**Metrics / Benchmarking System:**
------------------------------------
The /query-multi endpoint serves as part of a benchmarking API that evaluates multiple language models on code generation quality. It runs a given query across all configured models, measures performance (time duration, response length, quality score based on lint validation), and applies refinement iterations to assess improvement. The aggregated results provide a standardized benchmark for comparing model accuracy and code quality.  

**DISCLAIMER **
---------------
Model comparisons in this repository across documents, code, or media are for illustrative purposes only. The metrics generated for the best response are specific to a given run and may vary because LLM behavior is non-deterministic. Any compatible model can produce an error‑free response with this framework at any time. Therefore, we make no claims about intrinsic model quality and do not endorse any vendor.
