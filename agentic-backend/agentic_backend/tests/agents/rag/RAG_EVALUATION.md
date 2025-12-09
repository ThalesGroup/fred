# RAG Evaluation Script

This script evaluates Retrieval-Augmented Generation (RAG) agents using the [DeepEval](https://deepeval.com/) framework. It allows you to assess agent performance on a set of questions using various RAG metrics.

## Features

- Evaluates RAG agents using multiple RAGAS metrics:
  - Answer Relevancy : Measures how relevant the generated answer is to the user’s question.
  - Faithfullness : Measures how factually consistent the answer is with the retrieved context.
  - Contextual Precision : Measures how much of the retrieved context is actually useful for generating the answer
  - Contextual Recall : Measures whether the retrieved context contains all the information needed to answer correctly.
  - Contxtual Relevancy : Measures how relevant the retrieved context is to the question itself (not to the final answer).
- Supports custom chat and embedding models
- Configurable document libraries for agent context

## Requirements

- Launching the knowledge flow and uploading documents 
- The script uses the application's configuration file to set up models and agents. Ensure this file is properly configured with your model settings.

## Architecture

### BaseEvaluator Class

Abstract base class providing the core evaluation infrastructure:

- Configuration management (YAML)
- LLM model loading (Ollama, OpenAI)
- JSON dataset handling
- Colored logging
- Automatic metric averaging

### RAGEvaluator Class

Specific implementation for RAG agent evaluation

## Usage

```bash
python rag_advanced_evaluation.py \
  --chat_model "gpt-4" \
  --embedding_model "text-embedding-3-small" \
  --dataset_path "tests/agents/rag/test_questions.json"
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--chat_model` | Yes | Name of the chat model to use |
| `--embedding_model` | Yes | Name of the embedding model to use |
| `--dataset_path` | Yes | Path to the JSON test file |
| `--doc_libs` | No | Comma-separated list of document library IDs |
| `--configuration_file` | No | Name of the configuration file (default: configuration.yaml) |

### Test Dataset Format

The test dataset should be a JSON file with the following structure:

```json
[
  {
    "question": "What is the capital of France?",
    "expected_answer": "The capital of France is Paris."
  },
  ...
]
```

## Output

The script outputs evaluation results in a formatted table showing scores for each metric. Example:

```
📈 DEEPEVAL EVALUATION RESULTS
======================================================================
AVERAGES PER METRIC
======================================================================
Answer Relevancy
──────────────────────────────────────────────────────────────────────
  Average:           0.8333 (83.33%)

Contextual Precision
──────────────────────────────────────────────────────────────────────
  Average:           1.0000 (100.0%)

Contextual Recall
──────────────────────────────────────────────────────────────────────
  Average:           0.0000 (0.0%)

Contextual Relevancy
──────────────────────────────────────────────────────────────────────
  Average:           0.1905 (19.05%)

Faithfulness
──────────────────────────────────────────────────────────────────────
  Average:           0.8000 (80.0%)

======================================================================
OVERALL AVERAGE
======================================================================
  Overall average:   0.5648 (56.48%)
```

## Extension

To create a new evaluator, inherit from BaseEvaluator:

```
class CustomEvaluator(BaseEvaluator):
    async def run_evaluation(self, agent_name: str, doc_lib_ids: list[str] | None = None):
        # Your implementation
        pass
```