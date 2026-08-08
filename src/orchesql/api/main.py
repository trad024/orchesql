"""FastAPI app for orchesql."""

from fastapi import FastAPI

app = FastAPI(title="orchesql")


@app.get("/health")
def health():
    return {"status": "ok"}


# Future: POST /query -- submit a natural language question, returns a
# session_id and either results or a clarification request.
# Future: POST /query/{session_id}/clarify -- resume a paused session
# with the user's answer to a clarification_request.
