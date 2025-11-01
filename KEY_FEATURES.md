The key features of CN-HyRAG  v1.0 are as listed here:

1. **Hybrid Semantic-Syntactic Parsing**
   - Combines AST-based syntactic parsing with embedding-based semantic chunking.
   - Preserves code structure while enabling semantic similarity search.
   - Multi-layer indexing: complete files for templates + chunks for details.

2. **Multi-Model Parallel Inference**
   - Queries up to MAX_REFINEMENT_ITERATIONS (default=3) models concurrently.
   - Supports both Azure OpenAI and OpenAI-compatible APIs.
   - Reduces single-model bias and increases output diversity.

3. **Self-Healing Code Generation**
   - Automatically detects errors using golangci-lint for static code analysis.
   - Iteratively refines responses until errors are resolved. Ends early if no errors are found.
   - Tracks improvement metrics across refinement cycles.

4. **Cloud Native-Ready Validation**  
   - Native golangci-lint integration.
   - Accurate error line counting (not just Issue objects).
   - Quality scoring based on actual linting results.

5. **Cloud-Native Architecture**
   - Containerized deployment with Docker Compose.
   - Qdrant vector database for scalable indexing.
   - REST API for webhook/integration support.
   - Environment-based configuration.

6. **Go-First Language Support**
   - Optimized for Kubernetes client-go code generation.
   - Tree-sitter Go parser for accurate AST extraction.
   - Handles complex Go idioms (error handling, contexts, interfaces).

