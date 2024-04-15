from llama_index.core import VectorStoreIndex, Settings, StorageContext
from llama_index.readers.github import GithubClient, GithubRepositoryReader
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.readers.web import WholeSiteReader
from qdrant_client import QdrantClient
from dotenv import load_dotenv
from tqdm import tqdm
import httpx
import sys
import os

load_dotenv()
github_client = GithubClient(os.getenv('GITHUB_TOKEN'))
client = QdrantClient(os.getenv('QDRANT_URL'), api_key=os.getenv('QDRANT_API'))
print("Initialized successfully. Loading embedding model...")
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")
print("Embedding model loaded successfully. Setting up vector store index...")
repos_config = [
    {
        "owner": "twilsonco",
        "repo": "openpilot",
        "branch": "log-info",
        "filter_directories": (["sec"], GithubRepositoryReader.FilterType.INCLUDE),
        "filter_file_extensions": ([".md"], GithubRepositoryReader.FilterType.INCLUDE),
    },
    {
        "owner": "commaai",
        "repo": "openpilot-docs",
        "branch": "master",
        "filter_directories": (["docs"], GithubRepositoryReader.FilterType.INCLUDE),
        "filter_file_extensions": ([".md"], GithubRepositoryReader.FilterType.INCLUDE),
    },
    {
        "owner": "commaai",
        "repo": "comma10k",
        "branch": "master",
        "filter_directories": (["imgs", "imgs2", "imgsd", "masks", "masks2", "masksd"], GithubRepositoryReader.FilterType.EXCLUDE),
        "filter_file_extensions": ([".png", ".jpg"], GithubRepositoryReader.FilterType.EXCLUDE),
    },
    {
        "owner": "FrogAi",
        "repo": "FrogPilot",
        "branch": "FrogPilot-Development",
        "filter_directories": (["selfdrive", "README.md", "docs", "tools"], GithubRepositoryReader.FilterType.INCLUDE),
        "filter_file_extensions": ([".py", ".md", ".h", ".cc"], GithubRepositoryReader.FilterType.INCLUDE),
    },
]

all_docs = {}

for config in tqdm(repos_config, desc="Loading documents from repositories"):
    try:
        loader = GithubRepositoryReader(
            github_client,
            owner=config["owner"],
            repo=config["repo"],
            filter_directories=config["filter_directories"],
            filter_file_extensions=config["filter_file_extensions"],
            verbose=False,
            concurrent_requests=10,
            timeout=10,
            retries=3,
        )
        documents = loader.load_data(branch=config["branch"])
        all_docs.update({f"{config['owner']}/{config['repo']}": documents})
    except httpx.ConnectTimeout:
        print(f"Connection timeout for {config['owner']}/{config['repo']}.", file=sys.stderr)
        sys.exit(1)

# Scrape the wiki
scraper = WholeSiteReader(
    prefix="https://github.com/commaai/openpilot/wiki/", max_depth=2
)
wiki = scraper.load_data(
    base_url="https://github.com/commaai/openpilot/wiki"
)
all_docs.update({"wiki": wiki})

print("Data downloaded successfully. Setting up Qdrant vector store...")
vector_store = QdrantVectorStore(client=client, enable_hybrid=True, batch_size=20, collection_name="openpilot-data-sparse")
storage_context = StorageContext.from_defaults(vector_store=vector_store)

# Flatten the all_docs dictionary
documents = []
for repo_docs in tqdm(all_docs.values(), desc="Flattening documents"):
    documents.extend(repo_docs)

print("Documents flattened successfully. Setting up index...")
# Insert the documents into the index
index = VectorStoreIndex.from_documents(documents, storage_context=storage_context, show_progress=True)
print("Index setup complete.")