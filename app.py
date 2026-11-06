import re
import joblib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

MODEL_FILE = "fake_news_classifier.pkl"
VECTORIZER_FILE = "tfidf_vectorizer.pkl"

print("Loading pre-trained model into memory...")
classifier = joblib.load(MODEL_FILE)
vectorizer = joblib.load(VECTORIZER_FILE)
print("Server ready!")

app = FastAPI(title="Fake News Detection API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def preprocess(article: str) -> str:
    article = str(article).lower()
    article = re.sub(r"^.*?\(reuters\)\s*-?\s*", "", article)
    article = re.sub(r"http\S+|www\S+", "", article)
    article = re.sub(r"[^a-z\s]", "", article)
    article = re.sub(r"\s+", " ", article).strip()
    return article

class NewsInput(BaseModel):
    text: str = Field(..., min_length=10)

@app.post("/predict")
def predict_news(payload: NewsInput):
    words = payload.text.strip().split()
    if len(words) < 5:
        raise HTTPException(status_code=400, detail="Please enter at least 5 words.")
    
    cleaned = preprocess(payload.text)
    features = vectorizer.transform([cleaned])
    probabilities = classifier.predict_proba(features)[0]
    
    fake_prob = float(probabilities[0])
    real_prob = float(probabilities[1])
    label = "REAL" if real_prob >= 0.5 else "FAKE"
    
    return {
        "label": label,
        "fake_probability": round(fake_prob * 100, 2),
        "real_probability": round(real_prob * 100, 2),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)