```
A deep dive into the Architecture of Cloud Native - Hybrid RAG comprising 
of multiple phases are discussed here:
--------------------------------------------------------------------------
Phase 1 -- Knowledge base ingestion: 
The pipeline goes like this:  
[Ingestion → 
     → Full File Indexing → 
         → Syntactic Parsing → 
             → Semantic Chunking → 
                 → Unified Vector Store (Qdrant) ], 
where in Go source files with some patterns are ingested into the framework 
through this component. Further the source code is subjected to multi layered 
processing as in to create file nodes for holistic template matching, 
syntactic nodes, and semantic chunks giving it a rich, multi-resolution 
knowledge of code structure and meaning. This approach allows queries to 
leverage coarse templates and fine-grained details at the same time, 
enabling precise and flexible retrieval for generation and validation.
    The layers are:
        a> Complete File Indexing: Each source file is indexed as an entire 
        unit (FULL file nodes), preserving module-level patterns, import 
        structures, and context for use as full templates or architectural 
        references. These nodes have CRITICAL priority and are always 
        retrieved for prompt context as “structural templates.”
        
        b> Syntactic parsing: Each file is parsed with Tree-sitter to extract 
        AST-based sections: functions, types, methods, constants, vars, 
        and imports. This syntactic layer enables the framework to answer or 
        generate code for specific constructs and structural elements, 
        supporting queries that target defined code boundaries.
        
        c> Semantic chunking: Large syntactic chunks are further subdivided 
        using embedding-based semantic similarity creating meaning-aware 
        segments even inside functions/types. This semantic layer splits 
        code into contextually coherent fragments, providing high-resolution 
        matching for conceptual, behavioural, or domain-specific queries.
        
Finally all indexed nodes are pushed into Qdrant vector database with 
metadata forming the KB for RAG. 

Phase II -- Validation and Model selection: 
The pipeline goes like this:  
[Model Responses → 
     → Static Validation (golangci-lint)→  
         → Quality Scoring (3 metrics) → 
             → Combined Ranking (weighted) → 
                 →Best Model Selection]. 
Each model's response is subjected to static code analysis through "golangci-lint" 
where temporary code sandbox gets created with go.mod for JSON based results 
generation. The output of linting comprises of issues reported, errors, and other 
metadata including error messages and line numbers. The issues obtained are then 
passed for weighted quality scoring and best response selection based on the 
following computations:
    -- Quality Score (70% weight): 1.0 - (errors * 0.08) from golangci-lint. 
        Errors showing up beyond 12 are rated poor.
    -- Speed Score (10% weight): max(0.0, 1.0 - (duration/30))
    -- Completeness Score (20% weight): min(length/3000, 1.0)
    Combined Score: 0.70*quality + 0.10*time + 0.20*completeness.
The best response is selected across ranked list of responses along with 
validation metadata. 

Phase III -- Multi-Model Query Pipeline: 
The pipeline goes like this: 
[User Query → 
     → Context Retrieval (top-k=15)-> 
         → [model-A]-> 
         → [model-B]->
         → [model-C]->
             → Parallel response generation]. 
The system retrieves the top 15 most relevant nodes from Qdrant, combining 
up to 2 complete files and 8 chunks to build a hierarchical prompt where full 
files guide structure and chunks add detail. All models run in parallel via 
ThreadPoolExecutor—Azure models using LlamaIndex’s AzureOpenAI client and 
others through an OpenAI-compatible interface with custom base URLs. 
A system prompt enforces structural and idiomatic Go patterns, while 
responses are cleaned, extended if truncated, and enriched with metadata 
such as context size, response length, and generation stats, typically 
producing 3 parallel model outputs.

Phase IV -- Validation & Model Selection: 
The process flows like this: 
[ Model Responses → 
    → Static Validation (golangci-lint)→  
        → Quality Scoring (3 metrics) →  
            → Combined Ranking (weighted) →  
                → Best Model Selection ]
The validation pipeline runs golangci-lint in a temporary Go workspace to 
detect and count real error lines from JSON output, extracting detailed 
messages with line numbers. It then computes a composite score combining 
Quality (70%, based on lint errors), Time (10%, based on generation speed), 
and Completeness (20%, based on response length). Models are ranked by this 
combined score, and the top result is marked as the best, with all 
responses output alongside their validation metadata.

Phase V ( Final ) -- Refinement & self-correction: The process flows like this,
Best Response → Has Errors? → No → Return Response
                      ↓ Yes
              Refinement Iteration 1
                      ↓
          Re-Validation (golangci-lint)
                      ↓
              Errors Fixed? → Yes → Return Refined
                      ↓ No
          Max Iterations? → Yes → Return Best Attempt
                      ↓ No
              Refinement Iteration 2
                      ↓
                    (loop)

The workflow begins by generating the best possible response based on current 
inputs. This response is then analysed for potential issues such as lint 
errors, logic flaws, or formatting inconsistencies. If no errors are detected, 
the response is immediately accepted and returned as final. However, if 
errors are found, the system enters an iterative refinement cycle. In each 
refinement iteration, the response is corrected and revalidated using 
golangci-lint to ensure that all detected issues are resolved. When the 
errors are fixed, the refined output is returned as the final version. 
If issues persist after revalidation, the process checks whether the 
maximum number of refinement iterations has been reached. If so, the system 
returns the best available attempt; otherwise, it proceeds to the next 
iteration and continues the improvement loop until the response passes 
validation or the iteration limit is reached.

```