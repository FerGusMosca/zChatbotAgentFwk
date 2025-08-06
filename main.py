import argparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from controllers import chat_controller
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Parse the --prompt argument
parser = argparse.ArgumentParser()
parser.add_argument("--prompt", type=str, default="generic_prompt")
args, _ = parser.parse_known_args()
prompt_path = f"prompts/{args.prompt}.txt"

with open(prompt_path, encoding="utf-8") as f:
    prompt_text = f.read()

    print(f"\n=== PROMPT CARGADO ===\n{prompt_text}\n======================\n")

# Store it in environment variable
os.environ["ZBOT_PROMPT_NAME"] = args.prompt
print(f">>> Prompt selected from CLI: {args.prompt}")

app = FastAPI()

# Templates (HTML)
templates = Jinja2Templates(directory="templates")

# Static files (CSS/JS/img)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Home page
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    print(">>> Renderizando main_page.html")  # Debug
    return templates.TemplateResponse("main_page.html", {"request": request})


# API router
app.include_router(chat_controller.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8081, reload=True)
