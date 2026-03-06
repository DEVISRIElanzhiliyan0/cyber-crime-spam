import pandas as pd
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.model_selection import train_test_split

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load Dataset (Kaggle SMS Spam Dataset)
data = pd.read_csv(os.path.join(BASE_DIR, "..", "spam.csv"), encoding='latin-1')
data = data[['v1','v2']]
data.columns = ['label','message']

data['label'] = data['label'].map({'ham':0,'spam':1})

X_train, X_test, y_train, y_test = train_test_split(
    data['message'], data['label'], test_size=0.2
)

vectorizer = TfidfVectorizer()
X_train_tfidf = vectorizer.fit_transform(X_train)

model = MultinomialNB()
model.fit(X_train_tfidf, y_train)

pickle.dump(model, open(os.path.join(BASE_DIR, "spam_model.pkl"),"wb"))
pickle.dump(vectorizer, open(os.path.join(BASE_DIR, "vectorizer.pkl"),"wb"))

print("Model Trained Successfully")