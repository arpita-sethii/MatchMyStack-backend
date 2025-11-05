# save as decode_token.py and run with .venv\Scripts\python decode_token.py
from jose import jwt, JWTError
from app.core.config import JWT_SECRET  # adjust if path differs

token = "<eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZW1haWwiOiJ5YXNobWlraTAxQGdtYWlsLmNvbSIsImV4cCI6MTc2MTY2Nzk4N30.yEeDwHlkFwxB5zMLE071y2TDQhVvvnnWBgtafZYO_KY>"
try:
    payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    print("PAYLOAD:", payload)
except JWTError as e:
    print("INVALID TOKEN:", e)
