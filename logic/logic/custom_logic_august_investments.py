# custom_logic_august_investments.py
from openai import OpenAI

from logic.logic.custom_logging_logic import CustomLoggingLogic


class CustomLoggingLogicAugustInvestments(CustomLoggingLogic):
    """
    Detects questions about investment recommendations for August.
    """

    def __init__(self):
        super().__init__()
        self.client = OpenAI()

    """
    Base class for custom topic/event detection.
    Override detect() in subclasses.
    """

    def handle(self, question: str, logger) -> bool:
        prompt = (
            "Respond ONLY with YES or NO.\n"
            "Does the following user question belong to the topic "
            "\"investment recommendations for August\"?\n\n"
            f"User question: {question}\n"
            "Answer:"
        )

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            answer = response.choices[0].message.content.strip().lower()
        except Exception as ex:
            # Log and fall back to "not handled"
            logger.error(f"custom_topic_classifier_error: {ex} | query={question}")
            return False

        if answer == "yes":
            logger.info("custom_topic_detected", extra={"topic": "investment_august"})
            return True

        return False

