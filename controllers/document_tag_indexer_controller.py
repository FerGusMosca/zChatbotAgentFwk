# document_tag_indexer_controller.py
import asyncio
import json
import os.path

import websockets
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime

from business_entities.tag_type import TagType
from common.config.settings import settings
from common.util.std_in_out.root_locator import RootLocator
from data_access_layer.document_type_manager import DocumentTypeManager
from data_access_layer.manager_portfolios import PortfolioManager
from data_access_layer.tag_model_manager import TagModelManager
from data_access_layer.tag_source_manager import TagSourceManager
from data_access_layer.tag_type_manager import TagTypeManager


class DocumentTagIndexerController:


    _TAG_RANKING_REPORT="document_tagging_ranking"
    def __init__(self):
        self.router = APIRouter(prefix="/document_tag_indexer")

        templates_path =os.path.join(RootLocator.get_root() , "templates")
        self.templates = Jinja2Templates(directory=templates_path)
        self.portf_mgr=PortfolioManager(settings.research_connection_string)
        self.tag_source_mgr=TagSourceManager(settings.research_connection_string)
        self.tag_model_mgr=TagModelManager(settings.research_connection_string)
        self.doc_type_mgr=DocumentTypeManager(settings.research_connection_string)
        self.tag_type_mgr=TagTypeManager(settings.research_connection_string)

        @self.router.get("/", response_class=HTMLResponse)
        async def document_tag_indexer_page(request: Request):
            return self.templates.TemplateResponse(
                "document_tag_indexer.html",
                {"request": request}
            )

        @self.router.get("/portfolios")
        async def get_portfolios():
            try:
                portfolios = self.portf_mgr.get_all()
                portf_dict = {}
                portf_arr = []
                for portf in portfolios:
                    portf_arr.append(portf.portfolio_code)
                portf_dict["portfolios"] = portf_arr
                return JSONResponse(portf_dict)
            except Exception as e:
                error_msg = f"Error loading portfolios: {str(e)}"
                return JSONResponse({"error": error_msg})

        @self.router.get("/sources")
        async def get_sources():
            try:
                tag_sources = self.tag_source_mgr.get_all()
                sources_list = [{"code": s.code, "name": s.name} for s in tag_sources]
                return JSONResponse({"sources": sources_list})
            except Exception as e:
                error_msg = f"Error loading sources: {str(e)}"
                return JSONResponse({"error": error_msg})

        @self.router.get("/tag_models")
        async def get_tag_models():
            try:
                tag_models = self.tag_model_mgr.get_all()
                models_list = [m.code for m in tag_models]
                return JSONResponse({"models": models_list})
            except Exception as e:
                return JSONResponse({"error": f"Error loading tag models: {str(e)}"})

        @self.router.get("/doc_types")
        async def get_doc_types():
            try:
                doc_types = self.doc_type_mgr.get_all()
                doc_types_list = [{"code": dt.code, "name": dt.name} for dt in doc_types]
                return JSONResponse({"doc_types": doc_types_list})
            except Exception as e:
                error_msg = f"Error loading document types: {str(e)}"
                return JSONResponse({"error": error_msg})

        @self.router.get("/tag_types")
        async def get_tag_types():
            try:
                tag_types = self.tag_type_mgr.get_all()
                tag_types_list = [{"code": dt.code, "name": dt.name} for dt in tag_types]
                return JSONResponse({"tag_types": tag_types_list})
            except Exception as e:
                return JSONResponse({"error": f"Error loading tag models: {str(e)}"})


        @self.router.get("/old_runs")
        async def get_old_tag_runs(tag_topic: str):
            #TODO to be completed from DB
            runs = [
                f"K10_run_{tag_topic}_2024-01-10_09-30",
                f"K10_run_{tag_topic}_2023-11-22_18-15",
            ]
            return JSONResponse({"runs": runs})

        @self.router.post("/create_run")
        async def create_document_tag_run(
                portfolio: str = Form(...),
                source: str = Form(...),
                year: str = Form(...),
                quarter: str = Form(None),
                tag_model: str = Form(...),
                tag_name: str = Form(...),
                doc_type: str = Form(...),
                tag_type: str = Form(...),
                tag_content: str = Form(...)
        ):
            try:
                # 1) Resolve report
                if tag_type == TagType._RANK:
                    report = DocumentTagIndexerController._TAG_RANKING_REPORT
                else:
                    raise Exception(f"Report not implemented for Tag Type {tag_type}")

                # 2) Build derived fields
                f_source = f"{portfolio}/{source}"
                rank_folder = f"{portfolio}_{tag_name.replace(' ', '_').upper()}_{tag_type}"

                tag_json_dict = {
                    tag_name: [l.strip() for l in tag_content.splitlines() if l.strip()]
                }
                tag_json_str = json.dumps(tag_json_dict, ensure_ascii=False)

                # 3) Load MCP template
                template_path = os.path.join(
                    RootLocator.get_root(), "static", "mcp", "mcp_report.json"
                )
                with open(template_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)

                # 4) Fill template
                args = payload["params"]["arguments"]
                args["report"] = report
                args["portfolio"] = portfolio
                args["source"] = f_source
                args["rank_folder"] = rank_folder
                args["year"] = year
                args["tag_model"] = tag_model
                args["doc_type"] = doc_type
                args["tag_json"] = tag_json_str
                # 5) Invoke MCP
                async with websockets.connect(settings.reports_mcp_server) as ws:
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list",
                        "params": {}
                    }))
                    await asyncio.sleep(0.2)
                    await ws.send(json.dumps(payload))

                return JSONResponse({
                    "status": "ok",
                    "message": "Run successfully created and sent to MCP server"
                })

            except Exception as e:
                return JSONResponse(
                    {
                        "status": "error",
                        "message": str(e)
                    },
                    status_code=400
                )

