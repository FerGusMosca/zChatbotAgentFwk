# File: cross_encoder_client.py
# Comments in English

import requests
from typing import List
from langchain_core.documents import Document
import logging

class CrossEncoderClient:
    """
    Client for remote cross-encoder reranker on RunPod Serverless.
    Full compatibility with local ChunkRelevanceFilter.is_relevant interface.
    """
    def __init__(self, url: str, api_key: str, logger=None):
        self.base_url = url.rstrip("/") + "/"
        self.api_key = api_key
        self.logger = logger or logging.getLogger(__name__)

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        self.endpoint = self.base_url + "runsync"

    def is_relevant(
        self,
        folder: str,
        query: str,
        docs: List[Document],
        file_logger=None
    ) -> List[float]:
        """
        Exact same interface and behavior as local ChunkRelevanceFilter.is_relevant.
        - Extracts page_content from docs
        - Calls remote /runsync
        - Attaches scores to doc.metadata["cross_encoder_score"]
        - Optional detailed logging
        - Returns list of scores
        """
        if not docs:
            return []

        # Extract texts exactly like the local version
        texts = [doc.page_content for doc in docs]

        payload = {
            "input": {
                "query": query,
                "texts": texts
            }
        }

        try:
            self.logger.info(f"Sending {len(texts)} documents to remote cross-encoder")
            response = requests.post(
                self.endpoint,
                json=payload,
                headers=self.headers,
                timeout=360
            )
            response.raise_for_status()

            data = response.json()

            if data.get("status") != "COMPLETED":
                self.logger.error(f"RunPod job failed: {data.get('status')}")
                scores = [0.0] * len(docs)
            else:
                scores = data.get("output", {}).get("scores", [0.0] * len(docs))

            if len(scores) != len(docs):
                self.logger.warning(f"Score length mismatch: {len(scores)} vs {len(docs)} docs")
                # Pad or truncate to match docs length
                if len(scores) < len(docs):
                    scores += [0.0] * (len(docs) - len(scores))
                else:
                    scores = scores[:len(docs)]

            # Attach scores to documents (exactly like local)
            for doc, score in zip(docs, scores):
                doc.metadata["cross_encoder_score"] = score

            # Optional sorted logging (identical to local)
            if file_logger:
                scored_pairs = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
                for doc, score in scored_pairs:
                    file_logger.print_cross_encoding_comp(folder, query, doc.page_content, score)

            self.logger.info(f"Remote reranking completed: {len(scores)} scores")
            return scores


        # Propagate errors so caller can handle them appropriately
        except requests.Timeout:
            self.logger.error("RunPod request timed out (possible cold start or overload)")
            raise
        except requests.HTTPError as e:
            self.logger.error(f"RunPod HTTP error {e.response.status_code}: {e.response.text}")
            raise
        except requests.RequestException as e:
            self.logger.error(f"RunPod connection/network error: {str(e)}")
            raise
        except (RuntimeError, ValueError, KeyError) as e:
            self.logger.error(f"RunPod response parsing error: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error in remote reranker: {str(e)}")
            raise