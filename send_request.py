import httpx

#send a request to localhost fastapi server 
"""{
"email": "your-email-id"
"secret": "your-secret-value"
"url": "https://en.wikipedia.org/wiki/Artificial_intelligence"
}"""

payload = {
    "email": "your-email-id",
    "secret": "my-secret-value",
    "url": "https://en.wikipedia.org/wiki/Artificial_intelligence"
}

response = httpx.post("http://localhost:8000/quiz", json=payload)

print("Response Status Code:", response.status_code)
print("Response JSON:", response.json())
