from datetime import datetime
from typing import List

import requests
from langchain.docstore.document import Document
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from flow import AgentFlow
from fred.application_context import get_agent_settings, get_model_for_agent
from fred.common.models.document_source import DocumentSource
from services.chatbot_session.structure.chat_schema import ChatSource

class DocumentsExpert(AgentFlow):
    """
    An expert agent that searches and analyzes documents to answer user questions.
    This agent uses a vector search service to find relevant documents and generates
    responses based on the document content.
    """
    name: str = "DocumentsExpert"
    role: str = "Documents Expert"
    nickname: str = "Dominic"
    description: str = "Extracts and analyzes document content to answer questions."
    icon: str = "documents_agent"
    categories: List[str] = []
    tag: str = "Innovation"

    def __init__(self):
        """
        Initialize the DocumentsExpert agent with settings and configuration.
        Loads settings from agent configuration and sets up connections to the
        knowledge base service.
        """
        self.agent_settings = get_agent_settings(self.name)
        self.knowledge_flow_url = self.agent_settings.settings.get(
            "knowledge_flow_url", "http://localhost:8111/knowledge/v1"
        )
        self.document_directory = self.agent_settings.settings.get("document_directory", "./resources/knowledge/imported")
        self.chunk_size = self.agent_settings.settings.get("chunk_size", 512)
        self.chunk_overlap = self.agent_settings.settings.get("chunk_overlap", 64)
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.vector_store_retriever = None
        self.categories = self.agent_settings.categories if self.agent_settings.categories else ["Documentation"]
        if self.agent_settings.tag:
            self.tag = self.agent_settings.tag

        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self.get_graph(),
            base_prompt=self._generate_prompt(),
            categories=self.categories,
            tag=self.tag
        )

    def _generate_prompt(self) -> str:
        """
        Generate the base prompt for the document expert agent.
        
        Returns:
            str: The base prompt for the agent.
        """
        return (
            "You are responsible for analyzing document parts and answering questions based on them.\n"
            "Whenever you reference a document part, provide citations.\n"
            f"The current date is {self.current_date}.\n"
        )

    async def agent(self, state: MessagesState):
        """
        Main agent function that processes user questions and retrieves relevant documents.
        
        Args:
            state (MessagesState): The current state containing user messages.
            
        Returns:
            dict: A dictionary containing the agent's response message.
        """
        model = get_model_for_agent(self.name)
        question: str = state["messages"][-1].content
        
        try:
            # Step 1: Send request to vector search service
            print(f"Sending request to {self.knowledge_flow_url}/vector/search with query: {question}")
            response = requests.post(
                f"{self.knowledge_flow_url}/vector/search",
                json={"query": question, "top_k": 10},
                timeout=10
            )
            response.raise_for_status()
            
            # Step 2: Process the response
            documents_data = response.json()
            print(f"Received response with {len(documents_data)} documents")
            
            # Step 3: Handle empty results
            if not documents_data:
                ai_message = await model.ainvoke([HumanMessage(content=
                    f"I couldn't find any relevant documents for your question about '{question}'. "
                    "Could you rephrase or ask another question?"
                )])
                return {"messages": [ai_message]}
            
            # Step 4: Process documents with error handling
            documents = []
            sources: List[ChatSource] = []
            
            for doc in documents_data:
                try:
                    # Handle field name differences (uid vs document_uid)
                    if "uid" in doc and "document_uid" not in doc:
                        doc["document_uid"] = doc["uid"]
                    
                    # Create DocumentSource instance
                    doc_source = DocumentSource(**doc)
                    documents.append(doc_source)
                    
                    # Create ChatSource for metadata
                    source = ChatSource(
                        document_uid=getattr(doc_source, "document_uid", getattr(doc_source, "uid", "unknown")),
                        file_name=doc_source.file_name,
                        title=doc_source.title,
                        author=doc_source.author,
                        content=doc_source.content,
                        created=doc_source.created,
                        type=doc_source.type,
                        modified=doc_source.modified or "",
                        score=doc_source.score
                    )
                    sources.append(source)
                except Exception as e:
                    print(f"Error processing document: {str(e)}. Document: {doc}")
            
            # Step 5: Check if we have any valid documents after processing
            if not documents:
                ai_message = await model.ainvoke([HumanMessage(content=
                    "I found some documents but couldn't process them correctly. Please try again later."
                )])
                return {"messages": [ai_message]}
            
            # Step 6: Build prompt with document content
            documents_str = ""
            for doc in documents:
                documents_str += (
                    f"Source file: {doc.file_name}\n"
                    f"Page: {doc.page}\n"
                    f"Content: {doc.content}\n\n"
                )
            
            prompt = (
                "You are an assistant that answers questions based on retrieved documents.\n"
                "Use the following related documents to generate your answer and cite sources.\n\n"
                f"{documents_str}\n"
                f"Question:\n{question}\n\n"
            )
            
            # Step 7: Generate response using the LLM
            response = await model.ainvoke([HumanMessage(content=prompt)])
            response.response_metadata.update({"sources": [s.model_dump() for s in sources]})
            return {"messages": [response]}
            
        except requests.RequestException as e:
            # Handle API request errors
            print(f"Error connecting to vector search service: {str(e)}")
            error_message = await model.ainvoke([HumanMessage(content=
                "I couldn't access the document search service. Please try again later."
            )])
            return {"messages": [error_message]}
        except Exception as e:
            # Handle any other unexpected errors
            print(f"Unexpected error in DocumentsExpert agent: {str(e)}")
            error_message = await model.ainvoke([HumanMessage(content=
                "An error occurred while processing your request. Please try again later."
            )])
            return {"messages": [error_message]}

    def get_graph(self) -> StateGraph:
        """
        Create the LangGraph workflow for this agent.
        
        Returns:
            StateGraph: The graph defining the agent's workflow.
        """
        builder = StateGraph(MessagesState)
        builder.add_node("agent", self.agent)
        builder.add_edge(START, "agent")
        builder.add_edge("agent", END)
        return builder