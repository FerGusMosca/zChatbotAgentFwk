from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from logic.bot_engine import load_bot_for_client

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])

@router.post("/ask")
async def ask_question(request: Request):
    try:
        payload = await request.json()
        question = payload.get("question")

        if not question:
            raise HTTPException(status_code=400, detail="Missing 'question' in request body")

        # Load chain and run
        qa_chain = load_bot_for_client("demo_client")
        result = qa_chain.invoke({"question": question})
        return JSONResponse(content={"answer": result["answer"]})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
