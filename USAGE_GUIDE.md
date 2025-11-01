

```

A simple quick try for the 

1. Download the code:

```
git clone https://github.com/aulabsindia/CloudNativeAI/
cd src
```

2. Edit .env to update:
    a. YOUR_API_KEY
    b. YOUR-END_POINT url
    c. MODEL name
    d. MODEL deployment
    e. MODEL TYPE
    f. MMOEL version
    g. Embedding Model

You may include additional models if needed. keep it to max 4 for better validation and refinement 
turn around time. 

3. Load the ./feeds path with Golang source files holding patterns for building RAG knowledge base.
Try this: 
    a. Download DEMO kit.
        git clone github.com/aulabsindia/k8s-demo-tools
    b. The DEMO kit has has handlers to list pod, deployments, secrets and pod-service mapper utilities.
        Copy the files from ./handlers to ./feeds. 

4. Build RAG index :
   curl -s -X POST http://localhost:5001/build \
  -H "Content-Type: application/json" \
  -d '{"directory": "/workspace/feeds"}' | jq

5. Verify vector database:
    curl -s http://localhost:5001/verbose | jq

6. Generate response on user query: (try this)
    curl -s -X POST http://localhost:5001/query \
    -H "Content-Type: application/json" \
    -d '{"query":""Generate a handler to list ingress resources with hosts, paths, backend services, and load balancer IPs using cient-go." }'

Further to experiment the response generated. 
1. Place the response as ingress-lister.go in ./handlers of DEMO kit.
2. Run :
    go mod tidy
3. Build : 
    go build
4. Create sample ingress:
    kubectl apply -f ./samples/create-ingress.yaml
4. Invoke the ingress lister and cross verify across "kubectl get ingress --n default"
    ./k8s-demo-tools --handler ingress-lister  --namespace default

Task complete & verified !

```
