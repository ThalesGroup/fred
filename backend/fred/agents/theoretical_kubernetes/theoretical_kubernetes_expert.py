from datetime import datetime
from typing import List

from common.structure import AgentSettings
from flow import AgentFlow
from langchain_core.messages import SystemMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph import MessagesState, StateGraph, START, END
from langchain.docstore.document import Document
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_core.vectorstores import InMemoryVectorStore
from tiktoken import encoding_for_model
from langchain_openai import OpenAIEmbeddings
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.vectorstores import VectorStoreRetriever

from fred.application_context import get_agent_settings, get_model_for_agent

def load_documents(directory_path: str) -> List[Document]:
        """
        Load all markdown documents from a directory.

        Args:
            directory_path: Path to the directory containing the markdown files.
        """
        loader = DirectoryLoader(directory_path, glob="**/*.md", loader_cls=TextLoader)
        docs = loader.load()
        return docs


def split_documents(documents: List[Document]) -> List[List[Document]]:
    """
    Split the markdown documents into chunks based on the headers.

    Args:
        documents: List of documents to be split.
    """
    headers_to_split_on = [
        ("#", "1"),
        ("##", "2"),
        ("###", "3"),
    ]

    splitter = MarkdownHeaderTextSplitter(headers_to_split_on)

    splitted_docs = []
    for doc in documents:
        splitted_docs.append(splitter.split_text(doc.page_content))

    return splitted_docs


def document_size(document: Document, model: str) -> int:
    """
    Calculate the size of a document in tokens.

    Args:
        document: The document to calculate the size of.
        model: The model to use for encoding.
    """
    content = document.page_content
    enc = encoding_for_model(model)
    tokens = enc.encode(content)

    return len(tokens)


def group_split(split: List[Document], token_limit: int, model: str) -> List[List[Document]]:
    """
    Group the split documents into groups of documents that are less than the token limit.

    Args:
        split: List of documents to be grouped.
        token_limit: The maximum number of tokens allowed in a group.
        model: The model to use for encoding.
    """
    i = 0
    result = []

    while i < len(split):
        grouped_documents_size = 0
        grouped_documents = []

        while i < len(split) and grouped_documents_size + document_size(split[i], model) <= token_limit:
            grouped_documents.append(split[i])
            grouped_documents_size += document_size(split[i], model)
            i += 1

        if not grouped_documents:
            grouped_documents.append(split[i])
            grouped_documents_size += document_size(split[i], model)
            i += 1

        result.append(grouped_documents)

    return result


def create_chunks(grouped_splits: List[List[Document]]) -> List[str]:
    """
    Create chunks from the grouped splits, preserving headers context without duplication.

    Args:
        grouped_splits: List of grouped splits (each group is a list of Documents).

    Returns:
        List of chunk strings.
    """
    chunks = []

    for split in grouped_splits:
        chunk = ""

        for doc in split:
            if doc.metadata.get("1", None):
                chunk += f"{doc.metadata['1']}"
            if doc.metadata.get("2", None):
                chunk += f" - {doc.metadata['2']}"
            if doc.metadata.get("3", None):
                chunk += f" - {doc.metadata['3']}"

            chunk += "\n\n"
            chunk += doc.page_content
    
        chunks.append(chunk)

    return chunks


def build_vector_store_retreiver(directory_path: str, chunk_size: int, tokenizer_model: str) -> VectorStoreRetriever:
    """
    Build a vector store retriever for the Kubernetes documentation.

    Returns:
        VectorStoreRetriever: The vector store retriever.
    """
    docs = load_documents(directory_path)

    splitted_docs = split_documents(docs)

    grouped_splits = []
    for split in splitted_docs:
        grouped_splits.append(group_split(split, chunk_size, tokenizer_model))

    chunks = []
    for grouped_split in grouped_splits:
        chunks.extend(create_chunks(grouped_split))

    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-large",
    )

    vectorstore = InMemoryVectorStore.from_texts(
        chunks,
        embedding=embeddings,
    )

    return vectorstore.as_retriever()


class TheoreticalKubernetesExpert(AgentFlow):
    """
    Theoretical Kubernetes Expert able to extract official information, best practices and
    theoretical knowledge from the latest Kubernetes documentation.
    """
    # Class-level attributes for metadata
    name: str = "TheoreticalKubernetesExpert"
    role: str = "Theoretical Kubernetes Expert"
    nickname: str = "Theo"
    description: str =("Theoretical Kubernetes Expert able to extract official information, best "
                "practices and theoretical knowledge from the latest Kubernetes "
                "documentation.")
    icon: str = "kubernetes_agent"
    categories: list[str] = []
    tag: str = "Frugal IT"

    def __init__(self):
        """
        Initialize the Theoretical Kubernetes Expert.
        """
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        agent_settings = get_agent_settings(self.name)
        self.categories = agent_settings.categories if agent_settings.categories else ["Kubernetes"]
        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self.get_graph(),
            base_prompt=self._generate_prompt(),
            categories=self.categories,
        )

    def _generate_prompt(self) -> str:
        """
        Generates the base prompt for the Kubernetes expert.

        Returns:
            str: A formatted string containing the expert's instructions.
        """
        return (
            "You are a theoretical Kubernetes expert.\n"
                "You have access to the latest Kubernetes documentation.\n"
                "Your role is to anwser with precision and clarity on theoretical questions.\n"
                "If you found the information in the official Kubernetes documentation, "
                "please provide the source when available.\n"
                "In case of graphical representation, render mermaid diagrams code.\n\n"
                f"The current date is {self.current_date}.\n"
        )

    async def agent(self, state: StateGraph):
        """
        Invokes the agent model to generate a response based on the current state.

        The model might decide to use the retreiver tool to fetch relevant documents.

        Args:
            state (messages): The current state.

        Returns:
            dict: The updated state with the agent response appended to messages.
        """
        model = get_model_for_agent(self.name)

        # TODO: Make this stateless by using a separate vectorstore.
        # For the moment, it rebuilds an in-memory vectorstore for each question.
        # This is not efficient at all.
        vector_store_retreiver = build_vector_store_retreiver(
            directory_path="./resources/knowledge/kubernetes",
            chunk_size=1024,
            tokenizer_model="gpt-4o",
        )

        question = state["messages"][-1].content
        context = vector_store_retreiver.invoke(question)[0].page_content.replace("\n", " ").replace("\r", " ")

        response = await model.ainvoke(state["messages"])

        system_prompt = (
            f"You are an assistant for question-answering tasks. "
            f"Use the following pieces of retrieved context to answer the question. "
            f"If you don't know the answer, just say that you don't know. "
        )

        user_prompt = (
            f"Question:\n{question}\n\n"
            f"Context:\n{context}\n\n"
            f"Answer:"
        )
        response = await model.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])

        return {
            "messages": [response],
        }

    def get_graph(self):
        builder = StateGraph(MessagesState)

        builder.add_node("agent", self.agent)

        builder.add_edge(START, "agent")
        builder.add_edge("agent", END)

        return builder

# import asyncio
# from langchain_core.messages import HumanMessage

# async def main():
#     # Create an instance of the TheoreticalKubernetesExpert
#     expert = TheoreticalKubernetesExpert()

#     app = expert.graph.compile()

#     messages = [HumanMessage(content="How finalizers work in Kubernetes ?")]

#     inputs = {
#         "messages": messages,
#     }

#     config = {"recursion_limit": 42}

#     async for event in app.astream(inputs, config=config, stream_mode="values"):
#         for m in event["messages"]:
#             m.pretty_print()

# if __name__ == "__main__":
#     asyncio.run(main())
