# RAGAS Evaluation Script

This script evaluates Retrieval-Augmented Generation (RAG) agents using the [RAGAS](https://docs.ragas.io/) framework. It allows you to assess agent performance on a set of questions using various RAGAS metrics.

## Features

- Evaluates RAG agents using multiple RAGAS metrics:
  - Faithfulness : Measures if the answer is factually grounded in the retrieved context.
  - Answer Relevancy : Measures if the answer directly addresses the question.
  - Context Precision : Measures if relevant documents are ranked first in the retrieved context.
  - Context Recall : Measures if all necessary information to answer is in the retrieved context.
  - Answer Similarity : Measures semantic similarity between the generated answer and expected answer.
- Supports custom chat and embedding models
- Configurable document libraries for agent context

## Requirements

- Launching the knowledge flow and uploading documents 
- The script uses the application's configuration file (`config/configuration.yaml`) to set up models and agents. Ensure this file is properly configured with your model settings.

## Usage

```bash
python ragas_evaluation.py \
  --chat_model "gpt-4" \
  --embedding_model "text-embedding-3-small" \
  --dataset_path "tests/agents/rag/test_questions.json" \
  --doc_libs "lib1,lib2"
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--chat_model` | Yes | Name of the chat model to use |
| `--embedding_model` | Yes | Name of the embedding model to use |
| `--dataset_path` | Yes | Path to the JSON test file |
| `--doc_libs` | No | Comma-separated list of document library IDs |

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

The script outputs evaluation results in a formatted table showing scores for each metric with visual progress bars. Example:

```
📈 RAGAS EVALUATION RESULTS
======================================================================
  faithfulness         : ████████████████████░░ 0.920
  answer_relevancy     : ████████████████████░░ 0.880
  context_precision    : ████████████████████░░ 0.900
  context_recall       : ████████████████████░░ 0.850
  answer_similarity    : ████████████████████░░ 0.910
======================================================================
```