from __future__ import annotations
from typing import Dict, List
import os
from langchain_community.chat_models import ChatOpenAI

from common.util.downloader.google_drive_download import GoogleDriveDownload
from common.util.finder.google_contact_finder import GoogleContactFinder
from common.util.settings.env_deploy_reader import EnvDeployReader
from logic.intents.demos.intents_execution.portfolio_rotation.portfolio_rotation_execution_logic import \
    PortfolioRotationExecutionLogic


class PortfolioRotationIntentLogic:
    """
    Executor for 'portfolio_rotation' intent.
    - Downloads 'contacts_to_rotate.txt' from configured Drive folder
    - For each name, mock Google Contacts lookup
    - Returns confirmation messages
    """

    def __init__(self, logger, model_name="gpt-4o-mini", temperature=0.0):
        self.logger = logger
        self.llm = ChatOpenAI(model_name=model_name, temperature=temperature)
        self.contacts_file=EnvDeployReader.get("CONTACTS_FILE")
        self.message_file = EnvDeployReader.get("MESSAGE_FILE")

        self.folder_id = EnvDeployReader.get("DRIVE_FOLDER_ID").strip()
        if not self.folder_id:
            raise RuntimeError("Missing DRIVE_FOLDER_ID in environment")

    def required_slots(self) -> Dict[str, str]:
        return {}

    def try_extract(self, text: str):
        return {}

    def build_prompt_for_missing(self, missing: Dict[str, str]) -> str:
        return "Please provide missing info."


    def _download_ctcs_to_call(self):
        gdd = GoogleDriveDownload(logger=self.logger)
        local_contacts_file = gdd.download_file(self.contacts_file, self.folder_id)

        with open(local_contacts_file, "r", encoding="utf-8") as f:
            contacts = [line.strip() for line in f if line.strip()]

        if not contacts:
            return '{"answer":"No contacts found in file.","intent":"portfolio_rotation"}'

        return  contacts

    def _download_message(self) -> str:
        gdd = GoogleDriveDownload(logger=self.logger)
        message_file = gdd.download_file(self.message_file, self.folder_id)

        with open(message_file, "r", encoding="utf-8") as f:

            recommendation = " ".join(line.strip() for line in f if line.strip())

        if not recommendation:
            return '{"answer":"No portfolio recommendations file found.","intent":"portfolio_rotation"}'

        return recommendation

    def execute(self, slots: Dict[str, str]) -> str:
        try:

            # --- Download contacts file ---
            contacts= self._download_ctcs_to_call()
            rec_message=self._download_message()

            msgs = []
            for n in contacts:
                finder = GoogleContactFinder(logger=self.logger)
                contact = finder.find_contact(n)

                if contact:
                    # 👉 call the new execution logic here
                    execu = PortfolioRotationExecutionLogic(logger=self.logger)
                    result_json = execu.execute(contact, rec_message)

                    # keep both local info + execution result
                    msgs.append(f"Contactando a {contact['name']} ({contact['phone']})")
                    msgs.append(result_json)
                else:
                    msgs.append(f"❌ No se encontró WhatsApp para {n}")

                self.logger.info(f"[portfolio_rotation] Contacting {n}")

            return '{"answer":"' + " | ".join(msgs) + '","intent":"portfolio_rotation"}'
        except Exception as ex:
            self.logger.exception("portfolio_rotation_execute_error", extra={"error": str(ex)})
            return '{"answer":"❌ Error ejecutando portfolio rotation","intent":"portfolio_rotation"}'
