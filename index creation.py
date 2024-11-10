# index creation

from llama_index.core import VectorStoreIndex, Settings, StorageContext, SimpleDirectoryReader
from llama_index.readers.github import GithubClient, GithubRepositoryReader
from llama_index.vector_stores.weaviate import WeaviateVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.readers.file import PandasCSVReader
from contextlib import contextmanager
from core import config
from tqdm import tqdm
import weaviate
import httpx
import sys

github_client = GithubClient(config.read().get('GITHUB_TOKEN'))
Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small", api_key=config.read().get('OPENAI_API_KEY'))
WEAVIATE_URL = config.read().get("WEAVIATE_URL")

weaviate_client = weaviate.connect_to_local(
    host=WEAVIATE_URL,
    port=8080,
    grpc_port=50051
)

@contextmanager
def weaviate_connection(client):
    """Context manager for handling Weaviate client connections safely"""
    try:
        client.connect()
        yield client
    finally:
        try:
            client.close()
        except Exception as e:
            print(f"Warning: Error while closing Weaviate connection: {e}", file=sys.stderr)

'''WIKI DATA'''
with weaviate_connection(weaviate_client) as client:
    wiki_vector_store = WeaviateVectorStore(weaviate_client=client, index_name="Wiki")
    wiki_vector_store.delete_index()
    reader = SimpleDirectoryReader(input_dir="FrogWiki/", recursive=True)
    wiki_docs = reader.load_data(show_progress=True)
    print("Wiki data downloaded successfully. Setting up vector store for wiki...")
    wiki_storage_context = StorageContext.from_defaults(vector_store=wiki_vector_store)
    wiki_index = VectorStoreIndex.from_documents(wiki_docs, storage_context=wiki_storage_context, show_progress=True)
print("Wiki index setup complete.")

'''COMMIT DATA'''
with weaviate_connection(weaviate_client) as client:
    commit_vector_store = WeaviateVectorStore(weaviate_client=client, index_name="Commit")
    commit_vector_store.delete_index()
    reader = SimpleDirectoryReader(input_dir="CommitHistory", file_extractor={".csv": PandasCSVReader()})
    commit_docs = reader.load_data(show_progress=True)
    print("commit data downloaded successfully. Setting up vector store for commit...")
    commit_storage_context = StorageContext.from_defaults(vector_store=commit_vector_store)
    commit_index = VectorStoreIndex.from_documents(commit_docs, storage_context=commit_storage_context, show_progress=True)
print("commit index setup complete.")

'''GITHUB DATA'''
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
        "repo": "openpilot",
        "branch": "master-ci",
        "filter_directories": (["docs", "tools"], GithubRepositoryReader.FilterType.INCLUDE),
        "filter_file_extensions": ([".s"], GithubRepositoryReader.FilterType.EXCLUDE),
    },
    {
        "owner": "commaai",
        "repo": "openpilot",
        "branch": "release3",
        "filter_directories": (["selfdrive"], GithubRepositoryReader.FilterType.INCLUDE),
        "filter_file_extensions": ([".s"], GithubRepositoryReader.FilterType.EXCLUDE),
    }
]

for config in tqdm(repos_config, desc="Loading documents from repositories"):
    try:
        with weaviate_connection(weaviate_client) as client:
            index_name = f"{config['owner']}_{config['repo']}_{config['branch'].replace('-', '_')}".capitalize()
            github_vector_store = WeaviateVectorStore(weaviate_client=client, index_name=index_name)
            github_vector_store.delete_index()
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
            print(f"{config['owner']}/{config['repo']} data downloaded successfully. Setting up vector store...")
            github_storage_context = StorageContext.from_defaults(vector_store=github_vector_store)
            github_index = VectorStoreIndex.from_documents(documents, storage_context=github_storage_context, show_progress=True)
            print(f"Final index name: {index_name}")
            print(f"{config['owner']}/{config['repo']} index setup complete.")
    except httpx.ConnectTimeout:
        print(f"Connection timeout for {config['owner']}/{config['repo']}.", file=sys.stderr)
    except Exception as e:
        print(f"An error occurred while processing {config['owner']}/{config['repo']}: {e}", file=sys.stderr)