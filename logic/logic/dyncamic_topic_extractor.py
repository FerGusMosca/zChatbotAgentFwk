# dynamic_topic_extractor_llm.py
from openai import OpenAI
from logic.logic.custom_logging_logic import CustomLoggingLogic


class DynamicTopicExtractorLLM(CustomLoggingLogic):
    """
    Extracts a high-level topic name from the user question using an LLM.
    The LLM is instructed to return a short UPPER_SNAKE_CASE label
    representing the topic.  E.g. "COCINAR_PIZZAS", "JUGADORES_BOCA", etc.

    The label is logged and the method returns True (i.e. we consider the
    request 'handled' for logging purposes).
    """

    def __init__(self):
        self.client = OpenAI()

    def handle(self, question: str, logger) -> bool:
        prompt = (
            "You are a topic extractor.\n"
            "Given a user question, respond ONLY with a short high-level topic "
            "name in UPPER_SNAKE_CASE (max 3 words).  "
            "Do not include any explanations.\n\n"
            f"User question: {question}\n"
            "Answer:"
        )

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role":"user","content":prompt}],
                temperature=0.0
            )
            label = response.choices[0].message.content.strip().upper()
        except Exception as ex:
            logger.error(f"dynamic_topic_extractor_error: {ex} | query={question}")
            return False

        # Log the topic that was extracted
        logger.info(f"topic_detected --> topic:{label}", extra={"topic": label})
        return True
