# moving local

from llama_index.core import VectorStoreIndex, Settings, StorageContext, SimpleDirectoryReader
from llama_index.readers.github import GithubClient, GithubRepositoryReader
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.duckdb import DuckDBVectorStore
from llama_index.readers.file import PandasCSVReader
from dotenv import load_dotenv
from tqdm import tqdm
import httpx
import sys
import os

load_dotenv()
github_client = GithubClient(os.getenv('GITHUB_TOKEN'))
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5", device="cpu")

'''WIKI DATA'''
reader = SimpleDirectoryReader(input_dir="FrogWiki")
wiki_docs = reader.load_data()
print("Wiki data downloaded successfully. Setting up vector store for wiki...")
wiki_vector_store = DuckDBVectorStore(database_name="wiki.duckdb", persist_dir="./db_files")
wiki_storage_context = StorageContext.from_defaults(vector_store=wiki_vector_store)
wiki_index = VectorStoreIndex.from_documents(wiki_docs, storage_context=wiki_storage_context, show_progress=True)
print("Wiki index setup complete.")

'''COMMIT DATA'''
parser = PandasCSVReader()
file_extractor = {".csv": parser}
reader = SimpleDirectoryReader(input_dir="CommitHistory", file_extractor=file_extractor)
commit_docs = reader.load_data()
print("commit data downloaded successfully. Setting up vector store for commit...")
commit_vector_store = DuckDBVectorStore(database_name="commit.duckdb", persist_dir="./db_files")
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
        "repo": "comma-api",
        "branch": "master",
        "filter_directories": ([""], GithubRepositoryReader.FilterType.INCLUDE),
        "filter_file_extensions": ([".s"], GithubRepositoryReader.FilterType.EXCLUDE),
    },
    {
        "owner": "commaai",
        "repo": "openpilot",
        "branch": "master-ci",
        "filter_directories": (["selfdrive", "docs", "tools"], GithubRepositoryReader.FilterType.INCLUDE),
        "filter_file_extensions": ([".py", ".md", ".h", ".cc"], GithubRepositoryReader.FilterType.INCLUDE),
    },
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
        github_vector_store = DuckDBVectorStore(database_name=f"{config['owner']}_{config['repo']}.duckdb", persist_dir="./db_files")
        github_storage_context = StorageContext.from_defaults(vector_store=github_vector_store)
        github_index = VectorStoreIndex.from_documents(documents, storage_context=github_storage_context, show_progress=True)
        print(f"{config['owner']}/{config['repo']} index setup complete.")

    except httpx.ConnectTimeout:
        print(f"Connection timeout for {config['owner']}/{config['repo']}.", file=sys.stderr)
        sys.exit(1)