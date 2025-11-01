```
# Model 1 (Azure OpenAI Example)
# --------------------------------------------
MODEL_1_TYPE=azure_openai
MODEL_1_NAME=gpt-4o
MODEL_1_DEPLOYMENT=gpt-4o
MODEL_1_API_KEY=your-key
MODEL_1_ENDPOINT=https://your-endpoint.openai.azure.com
MODEL_1_API_VERSION=your-model-version


Model 2 (OpenAI-Compatible Example)
-----------------------------------------------------
MODEL_2_TYPE=openai_compatible
MODEL_2_NAME=llama
MODEL_2_DEPLOYMENT=llama-deployment
MODEL_2_API_KEY=your-key
MODEL_2_ENDPOINT=https://your-endpoint.openai.azure.com/v1


# Embedding Model (Shared)
AZURE_OPENAI_EMBEDDING_MODEL=text-embedding-3-large
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large-deployment
AZURE_OPENAI_EMBEDDING_API_VERSION=2024-02-01
AZURE_OPENAI_EMBEDDING_API_KEY=YOUR_API_KEY
AZURE_OPENAI_EMBEDDING_ENDPOINT=https://your-endpoint.openai.azure.com

# Vector Database configuration(Qdrant)
QDRANT_ENABLED=true
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=code_rag

# Server configurations:
FLASK_PORT=5001

# Refinement
MAX_REFINEMENT_ITERATIONS=4
```
