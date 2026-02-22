from azure.search.documents.indexes.models import *
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from pathlib import Path  
import os
from dotenv import load_dotenv
from langchain_community.vectorstores.azuresearch import AzureSearch
from langchain_openai import AzureOpenAIEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, PyMuPDFLoader, CSVLoader, UnstructuredXMLLoader, UnstructuredImageLoader, WebBaseLoader
from langchain_core.vectorstores import InMemoryVectorStore


if __name__ == "__main__":

    env_path = Path('.') / '.env'
    load_dotenv(dotenv_path=env_path)
    # Create credential (auto-detects Managed Identity in Container Apps)
    credential = DefaultAzureCredential()

    aisearchindexname = "bank"
    aisearchkey = os.getenv("AZURE_AI_SEARCH_KEY")
    openaikey = os.getenv("AZURE_OPENAI_API_KEY")
    openaiendpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    aisearchendpoint = os.getenv("AZURE_SEARCH_ENDPOINT") or os.getenv("AZURE_AI_SEARCH_SERVICE_ENDPOINT")
    aiapiversion = os.getenv("AZURE_OPENAI_API_VERSION")

    # Embedding config – fall back to main OpenAI endpoint / api-version if dedicated vars not set
    embeddingkey = os.getenv("AZURE_OPENAI_EMBEDDING_API_KEY")
    embeddingendpoint = os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT") or openaiendpoint
    embeddingname = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME") or "text-embedding-ada-002"
    embeddingapiversion = os.getenv("AZURE_OPENAI_EMBEDDING_API_VERSION") or aiapiversion

    # For Azure OpenAI embeddings
    token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")


print(aisearchindexname)

# Option 2: Use AzureOpenAIEmbeddings with an Azure account
embeddings: AzureOpenAIEmbeddings = AzureOpenAIEmbeddings(
    azure_deployment=embeddingname,
    openai_api_version=embeddingapiversion,
    azure_endpoint=embeddingendpoint,
    openai_api_key=None,
    azure_ad_token_provider=token_provider
)

# Specify additional properties for the Azure client such as the following https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/core/azure-core/README.md#configurations
vector_store: AzureSearch = AzureSearch(
    azure_search_endpoint=aisearchendpoint,
    azure_search_key=None,
    index_name=aisearchindexname,
    embedding_function=embeddings.embed_query,
    # Configure max retries for the Azure client
    additional_search_client_options={"retry_total": 4},
    credential=credential
)

# loader = TextLoader("./data/Claim_Approval_Rules.txt")
loader = PyPDFLoader("./db/bank_policies.pdf", extract_images=True)
# loader = PyMuPDFLoader("./data/Handwrittenform.pdf", extract_images=True)
# loader = CSVLoader("./data/RTG_Products.csv", encoding="utf-8")
# loader = UnstructuredXMLLoader("./data/AC.xml")
# loader = WebBaseLoader("https://www.truist.com/checking/premier-banking/financial-planning")

documents = loader.load()
text_splitter = CharacterTextSplitter(chunk_size=3095, chunk_overlap=100)
# text_splitter = CharacterTextSplitter(chunk_size=3095, chunk_overlap=100)
docs = text_splitter.split_documents(documents)
vector_store.add_documents(documents=docs)

# get_cosmosdb_vector_store().add_documents(documents=docs)

# Cleanup to avoid asyncio shutdown warning
del vector_store
print("Ingestion completed successfully.")
