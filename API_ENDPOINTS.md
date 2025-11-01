```
API Endpoints:
	--------------------------
	/build (POST)
	--------------------------
	Purpose: Build RAG index from code directory.
	Request:
	
	json
	{
  "directory": "./tools"
}
	Response:
	json
	{
  "files": 15,
  "nodes": 450,
	  "status": "index_built"
	}
	Errors: 
	400 -- Missing or empty ‘directory’ field in JSON body.
	500 -- No files found in /workspace/feeds
	
	Example:
	curl -X POST http://localhost:5001/build   -H "Content-Type: application/json"   \
    -d '{"directory": "/workspace/feeds"}' | jq
    
	--------------------------
	/verbose (GET)
	--------------------------
	Purpose: Get index status and configuration details
	Response:
	
	{
	  "available_models": [
	    "model-A",
	    "model-B",
	    "model-C"
	  ],
	  "built": true,
	  "files": 4,
	  "indexed_files": [
	    "/workspace/feeds/deployment_lister.go",
	    "/workspace/feeds/pod_lister.go",
	    "/workspace/feeds/podservice-mapper.go",
	    "/workspace/feeds/secret-lister.go"
	  ],
	  "nodes": 29
	}
	
	Example: 
	curl localhost:5001/verbose  -H "Content-Type: application/json" |jq
	Notes: when no files are indexed the indexed_files shows empty listing.
	
	--------------------------
	/query (POST)
	--------------------------
	Purpose: Get best model response with automatic refinement
	Request:
	
	json
	{
  "query": "Create a client-go  based handler for ingress-listing. "
}
	Response: Plain text Go code (refined if errors were detected)
	Process:
		-- Query all models in parallel.
		-- Validate all responses.
		-- Select best model.
		-- If errors detected, run iterative refinement.
		-- Return final refined (or original if no errors) response.
	
	Errors:
	400 -- Index not yet built; Call build first [when the vector index has not been 
    built via /build before invoking /query]
	500 -- No responses received; returned when the pipeline fails to obtain any 
    acceptable model after attempting generation or refinement. 

	Example: curl -X POST http://localhost:5001/query -H "Content-Type: application/json"   \
    -d '{"query": "Generate a handler to list ingress resources " }'
	
    --------------------------
	/query-multi (POST)
    --------------------------
	Purpose: Get detailed comparison across all models.
	Request:
	
	json
	{
  "query": "Create a client-go  based handler for ingress-listing. "
}
	Response:
	
	json
	{
  "query": "...",
  "models_queried": 3,
  "results": [
    {
      "model": "model-A",
      "response": "...",
      "duration": 3.45,
      "response_length": 2500,
      "quality_score": 0.92,
      "golangci_lint_errors": 1,
      "total_errors": 1,
      "has_errors": true,
      "errors": ["Line 45: undefined: metav1.ObjectMeta"],
      "refinement_info": {
        "refinement_performed": true,
        "iterations_performed": 2,
        "initial_errors": 1,
        "final_errors": 0,
        "refinement_successful": true,
        "total_improvement": 1
      }
    },
    ...
  ],
  "best_model": "model-A",
  "scoring_info": {
    "quality_score": "70% weight - golangci-lint validation",
    "time": "10% weight - response duration",
    "completeness": "20% weight - response length"
  }
}
	
	Errors:
	400 -- Index not yet built; 
    Call build first [when the vector index has not been built via /build before invoking /query-multi.]
	500 -- When unhandled exception occurs [ traceback logs in server side]
	200 OK -- Gives per model validation information.
	
	Example: 
    curl -X POST http://localhost:5001/query-multi  -H "Content-Type: application/json"   \
    -d '{"query": "Generate a handler to list ingress resources using client-go." }' | jq
	
Notes: The best model is computed from quality score and the configured scoring weights shown in 
scoring info, typically preferring fewer validation errors, sufficient completeness, and lower 
latency when scores are otherwise close
```