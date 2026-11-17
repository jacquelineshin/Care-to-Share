# Care-to-Share: AI Documentation

## 1. Overview

Care-to-Share integrates artificial intelligence to help users discover educational resources relevant to their documented health concerns.

The application uses a semantic similarity-based recommendation system. Rather than relying exclusively on exact keyword matches, the AI compares the meaning of user-provided health information with the content of available educational resources.

This allows the application to identify potentially relevant resources even when users describe their concerns using different wording from the educational materials.

## 2. AI Models and Services Used

### Sentence Transformers

The application uses the following pretrained model:

**Model:** `sentence-transformers/all-MiniLM-L6-v2`

**Library:** Sentence Transformers

**Underlying framework:** PyTorch

The model converts text into numerical representations called embeddings. Each embedding contains 384 dimensions that represent semantic information about the text.

These embeddings allow the application to compare the meaning of health concerns with the meaning of educational resources.

### Local Processing

The model runs locally on the application's machine using CPU processing.

The model is cached after its initial download, reducing the need to repeatedly download model files.

The recommendation system does not depend on an external generative AI API.

## 3. Model Selection Rationale

The `all-MiniLM-L6-v2` model was selected because it provides a practical balance between performance, processing requirements, and semantic understanding.

Reasons for selecting this model include:

- **Efficiency:** It is relatively lightweight compared with larger language models.
- **Semantic Understanding:** It can identify relationships between different phrases and descriptions.
- **Local Execution:** It can run without sending user health information to an external AI API.
- **Accessibility:** It is available through the Sentence Transformers library.
- **Cost:** It does not require paid API requests for each recommendation.

The model is suitable for a recommendation feature where the goal is to identify relevant educational content rather than generate medical diagnoses.

## 4. Input Preprocessing

Before generating recommendations, the application collects information associated with a user's health concern.

The information may include:

- Symptoms
- Symptom descriptions
- Frequency
- Duration
- Triggers
- Relief methods
- Additional questions or concerns
- Severity

The educational resources contain information such as:

- Resource title
- Description
- Topic
- Educational content

The application combines these text fields into descriptions that can be processed by the Sentence Transformer model.

The resulting text is converted into numerical embeddings so that the user's health concern and educational resources can be compared.

## 5. AI Processing Workflow

The recommendation process follows these steps:

### Step 1: Collect User Information

The application retrieves the user's documented health concern and associated symptom information.

### Step 2: Generate Text Embeddings

The Sentence Transformer model converts the health concern into a 384-dimensional embedding.

The same model is used to generate embeddings for educational resources.

### Step 3: Store Resource Embeddings

Educational resource embeddings are stored in the database so they can be reused instead of being regenerated unnecessarily.

### Step 4: Calculate Semantic Similarity

The application compares the user's embedding against the educational resource embeddings using normalized vectors and dot-product similarity.

This produces similarity scores representing how closely each resource relates to the user's health concern.

### Step 5: Filter and Rank Recommendations

The recommendation system uses a similarity threshold of 0.25 to filter results.

Resources that meet the threshold are ranked by their similarity scores.

The system returns up to five of the highest-ranking resources.

### Step 6: Display Recommendations

The selected educational resources are returned to the application for display to the user.

## 6. Output Handling

The AI produces ranked educational resource recommendations rather than medical diagnoses or treatment instructions.

The recommendation results are based on semantic similarity scores.

The system:

- Filters resources using the configured similarity threshold.
- Prioritizes resources with higher similarity scores.
- Limits the recommendation results to a maximum of five resources.
- Uses educational resources already available in the application's database.

If resources do not meet the similarity threshold, the system may return fewer than five recommendations or no recommendations.

## 7. Known Limitations

Although the recommendation system helps users discover relevant information, it has several limitations.

- **No Medical Diagnosis:** The model does not diagnose medical conditions or determine the cause of symptoms.
- **Context Limitations:** Semantic similarity does not guarantee that a resource is medically appropriate for every individual.
- **Resource Availability:** Recommendation quality depends on the accuracy, quality, and variety of educational resources stored in the database.
- **Model Limitations:** The selected model is a general-purpose sentence embedding model rather than a specialized medical language model.
- **Hardware Requirements:** Local processing requires sufficient memory and computing resources.
- **Similarity Threshold:** The 0.25 threshold may exclude some potentially relevant resources or include resources that are only loosely related.
- **Language Limitations:** The model may perform less reliably with languages or terminology that are not well represented in its training data.

## 8. Safety and Responsible AI Measures

Because Care-to-Share works with health-related information, responsible AI practices are important.

The application follows these principles:

- **Educational Purpose:** AI recommendations are intended to help users locate educational information, not replace professional medical advice.
- **No Automated Diagnosis:** The recommendation system does not identify diseases or prescribe treatments.
- **Local AI Processing:** User-provided text is processed locally by the recommendation model rather than being sent to an external AI API.
- **Relevant Information:** The system prioritizes educational materials based on similarity to the user's documented concerns.
- **Transparency:** Recommendations are presented as informational resources rather than guaranteed medical answers.
- **User Responsibility:** Users should consult qualified healthcare professionals when making decisions about their health.

## 9. AI Implementation Files

The main AI implementation is organized within the `ai_services` directory.

| File | Responsibility |
|---|---|
| `ai_services/resource_recommender.py` | Handles the AI-powered educational resource recommendation process. |
| `appointments/models.py` | Defines the application database models, including health concerns and educational resources. |
| `appointments/views.py` | Connects application requests and responses to the recommendation functionality. |

## 10. Summary

Care-to-Share uses a locally executed Sentence Transformer model to connect users with relevant educational resources.

By combining semantic embeddings, similarity scoring, database storage, and ranked recommendations, the application provides a practical example of integrating machine learning into a Django web application.

The AI system is designed to support health education and improve resource discovery while maintaining clear limitations around medical advice and diagnosis.