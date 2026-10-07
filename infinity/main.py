import os
import uvicorn
from dotenv import load_dotenv
from infinity_emb import create_server
from infinity_emb.args import EngineArgs

def main():
    # Load environment variables directly from the backend .env file to stay perfectly synced
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
    load_dotenv(env_path)

    # Initialize the Infinity Fastapi app with GPU support for multiple models
    
    # Engine for Reranking
    reranker_args = EngineArgs(
        model_name_or_path=os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"),
        engine="torch",
        device="auto",
        bettertransformer=False
    )
    
    # Engine for Embeddings
    embedding_args = EngineArgs(
        model_name_or_path=os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        engine="torch",
        device="auto",
        bettertransformer=False
    )
    
    # Load both models into the single Infinity server instance
    app = create_server(engine_args_list=[reranker_args, embedding_args])
    
    # Run the server on port 7997
    uvicorn.run(app, host="0.0.0.0", port=7997)

if __name__ == "__main__":
    main()
