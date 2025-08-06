from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from langchain_openai import ChatOpenAI

from logic.bot_engine import load_bot_for_client, load_hybrid_bot

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])

def get_openai_llm():
    return ChatOpenAI(temperature=0.3, model="gpt-4")
@router.post("/ask")
async def ask_question(request: Request, openai_llm=Depends(get_openai_llm)):
    try:
        payload = await request.json()
        question = payload.get("question")

        if not question:
            raise HTTPException(status_code=400, detail="Missing 'question' in request body")

        # Load the hybrid bot and its retriever
        hybrid_bot = load_hybrid_bot("demo_client")
        retriever = hybrid_bot.retriever

        # Retrieve documents and check if any are relevant
        docs_with_scores = retriever.vectorstore.similarity_search_with_score(query=question, k=1)

        if docs_with_scores:
            top_score = docs_with_scores[0][1]
            print(f"📚 Relevant document found in FAISS (score: {top_score}). Using QA chain.")
            result = hybrid_bot.handle(question)
            return JSONResponse(content={"answer": result})
        else:
            print("🔁 No relevant documents. Escalating to OpenAI LLM.")
            answer = openai_llm.predict(question)
            return JSONResponse(content={"answer": answer})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
