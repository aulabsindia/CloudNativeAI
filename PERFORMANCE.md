Performance Characteristics (Lab Results))

Indexing Performance
-- Small codebase (~5 files): 12-16 seconds
-- Medium codebase (~50 files): 30-60 seconds
-- Large codebase (~200 files): 2-4 minutes

Query Performance (Model dependent)
-- Model inference (parallel): 6-120 seconds 
-- Validation: 90-120 seconds per response
-- Refinement iteration: 60-120 seconds per iteration
-- Total end-to-end (with refinement): 2 - 7 mins ( Typical for complex queries)

Quality Metrics  (depends on model)
-- First-pass quality (no refinement): 75-90% responses error-free. 
-- After refinement (1-3 iterations): 95-100% responses error-free. 
    -- Most of the model response go for early stop here with good quality. 
-- Average refinement iterations: 2
-- Refinement success rate(2 Iterations): 95-99% 
-- Additional refinements (up to 5, temp=0.15): approach 100% error-free delivery for tough cases

Note
Performance may vary across environments and models. Results above reflect representative runs 
using our default lab configuration. We recommend benchmarking on your infrastructure when 
practical.