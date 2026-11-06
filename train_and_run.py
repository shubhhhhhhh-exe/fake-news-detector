import os
import re
import csv
import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

MODEL_FILE = "fake_news_classifier.pkl"
VECTORIZER_FILE = "tfidf_vectorizer.pkl"

def preprocess(article):
    article = str(article).lower()
    article = re.sub(r"^.*?\(reuters\)\s*-?\s*", "", article)
    article = re.sub(r"http\S+|www\S+", "", article)
    article = re.sub(r"[^a-z\s]", "", article)
    article = re.sub(r"\s+", " ", article).strip()
    return article

def load_isot():
    fake_df = pd.read_csv("Fake.csv")
    real_df = pd.read_csv("True.csv")
    fake_df["target"] = 0
    real_df["target"] = 1
    isot = pd.concat([fake_df, real_df], ignore_index=True)
    isot["full_text"] = isot["title"].fillna("") + " " + isot["text"].fillna("")
    return isot[["full_text", "target"]]

def load_ifnd():
    ifnd = pd.read_csv(
        "IFND.csv",
        encoding="latin-1",
        engine="python",
        on_bad_lines="skip",
    )
    ifnd.columns = [c.strip().lower() for c in ifnd.columns]
    ifnd["label"] = ifnd["label"].astype(str).str.strip().str.lower()
    ifnd = ifnd[ifnd["label"].isin(["true", "fake"])].copy()
    ifnd["target"] = (ifnd["label"] == "true").astype(int)
    ifnd["full_text"] = ifnd["statement"].fillna("")
    return ifnd[["full_text", "target"]]

def load_liar():
    cols = ["id", "label", "statement", "subject", "speaker", "job", "state",
            "party", "c1", "c2", "c3", "c4", "c5", "context"]
    frames = []
    for name in ["train.tsv", "valid.tsv", "test.tsv"]:
        if os.path.exists(name):
            frames.append(
                pd.read_csv(
                    name,
                    sep="\t",
                    header=None,
                    names=cols,
                    quoting=csv.QUOTE_NONE,
                    encoding="utf-8",
                    on_bad_lines="skip",
                )
            )
    liar = pd.concat(frames, ignore_index=True)
    fake_labels = ["pants-fire", "false", "barely-true"]
    real_labels = ["mostly-true", "true"]
    liar = liar[liar["label"].isin(fake_labels + real_labels)].copy()
    liar["target"] = liar["label"].isin(real_labels).astype(int)
    liar["full_text"] = liar["statement"].fillna("")
    return liar[["full_text", "target"]]

def train_model():
    print("Training model from datasets... Please wait.")
    isot = load_isot()
    ifnd = load_ifnd()
    liar = load_liar()
    print("ISOT:", len(isot), "| IFND:", len(ifnd), "| LIAR:", len(liar))

    news_df = pd.concat([isot, ifnd, liar], ignore_index=True)
    news_df = news_df.dropna().drop_duplicates(subset="full_text")
    news_df = news_df.sample(frac=1, random_state=42).reset_index(drop=True)
    news_df["processed"] = news_df["full_text"].apply(preprocess)
    news_df = news_df[news_df["processed"].str.len() > 0]

    train_text, test_text, train_labels, test_labels = train_test_split(
        news_df["processed"], news_df["target"],
        test_size=0.2, random_state=42, stratify=news_df["target"]
    )

    vectorizer = TfidfVectorizer(stop_words="english", max_df=0.7, max_features=80000, ngram_range=(1, 2))
    train_features = vectorizer.fit_transform(train_text)
    test_features = vectorizer.transform(test_text)

    classifier = LogisticRegression(max_iter=1000)
    classifier.fit(train_features, train_labels)

    predictions = classifier.predict(test_features)
    print(f"Test accuracy: {accuracy_score(test_labels, predictions):.2%}")

    joblib.dump(classifier, MODEL_FILE)
    joblib.dump(vectorizer, VECTORIZER_FILE)
    return classifier, vectorizer

# Load or Train Model
if os.path.exists(MODEL_FILE) and os.path.exists(VECTORIZER_FILE):
    print("Loading pre-trained model files...")
    classifier = joblib.load(MODEL_FILE)
    vectorizer = joblib.load(VECTORIZER_FILE)
else:
    classifier, vectorizer = train_model()

# FastAPI Setup
app = FastAPI(title="Fake News Detection API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    uvicorn.run(app, host="0.0.0.0", port=8000)