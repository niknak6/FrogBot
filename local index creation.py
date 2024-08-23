# local index creation using elasticsearch

from llama_index.core import VectorStoreIndex, Settings, StorageContext, SimpleDirectoryReader
from llama_index.readers.github import GithubClient, GithubRepositoryReader
from llama_index.vector_stores.elasticsearch import ElasticsearchStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.readers.file import PandasCSVReader
from elasticsearch import Elasticsearch
from core import read_config
from tqdm import tqdm
import torch
import httpx
import sys

github_client = GithubClient(read_config().get('GITHUB_TOKEN'))
device = "cuda" if torch.cuda.is_available() else "cpu"
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5", device=device)
es_url = read_config().get('ELASTICSEARCH_URL')
es_client = Elasticsearch(es_url)

def delete_all_indices(es_client):
    indices = es_client.indices.get_alias(index="*")
    for index in indices:
        es_client.indices.delete(index=index)
        print(f"Deleted index: {index}")

delete_all_indices(es_client)

'''WIKI DATA'''
reader = SimpleDirectoryReader(input_dir="FrogWiki", recursive=True)
wiki_docs = reader.load_data(show_progress=True)
print("Wiki data downloaded successfully. Setting up vector store for wiki...")
wiki_vector_store = ElasticsearchStore(
    index_name="wiki",
    es_url=es_url,
)
wiki_storage_context = StorageContext.from_defaults(vector_store=wiki_vector_store)
wiki_index = VectorStoreIndex.from_documents(wiki_docs, storage_context=wiki_storage_context, show_progress=True)
print("Wiki index setup complete.")

'''COMMIT DATA'''
parser = PandasCSVReader()
file_extractor = {".csv": parser}
reader = SimpleDirectoryReader(input_dir="CommitHistory", file_extractor=file_extractor)
commit_docs = reader.load_data(show_progress=True)
print("commit data downloaded successfully. Setting up vector store for commit...")
commit_vector_store = ElasticsearchStore(
    index_name="commit",
    es_url=es_url,
)
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
        "owner": "FrogAi",
        "repo": "FrogPilot",
        "branch": "MAKE-PRS-HERE",
        "filter_directories": (["selfdrive"], GithubRepositoryReader.FilterType.INCLUDE),
        "filter_file_extensions": ([".s"], GithubRepositoryReader.FilterType.EXCLUDE),
    },
    {
        "owner": "commaai",
        "repo": "openpilot",
        "branch": "master-ci",
        "filter_directories": (["docs", "tools"], GithubRepositoryReader.FilterType.INCLUDE),
        "filter_file_extensions": ([".s"], GithubRepositoryReader.FilterType.EXCLUDE),
    }
]

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

        print(f"{config['owner']}/{config['repo']} data downloaded successfully. Setting up vector store...")
        index_name = f"{config['owner']}_{config['repo']}".lower()
        github_vector_store = ElasticsearchStore(
            index_name=index_name,
            es_url=es_url,
        )
        github_storage_context = StorageContext.from_defaults(vector_store=github_vector_store)
        github_index = VectorStoreIndex.from_documents(documents, storage_context=github_storage_context, show_progress=True)
        print(f"{config['owner']}/{config['repo']} index setup complete.")

    except httpx.ConnectTimeout:
        print(f"Connection timeout for {config['owner']}/{config['repo']}.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred while processing {config['owner']}/{config['repo']}: {e}", file=sys.stderr)
        sys.exit(1)