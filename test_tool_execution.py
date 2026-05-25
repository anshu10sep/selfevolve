import asyncio
import logging
from typing import Type
from pydantic import BaseModel
from agents.analyst_agents import FundamentalAnalystAgent
from langchain_core.messages import AIMessage

logging.basicConfig(level=logging.INFO)

class MockLLM:
    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, messages):
        # Fake a tool call
        if not getattr(self, "called", False):
            self.called = True
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "analyze_financial_statements",
                    "args": {"ticker": "AAPL"},
                    "id": "call_123"
                }]
            )
        # Final response
        return AIMessage(content="Final fundamental analysis based on tools.")

    def with_structured_output(self, schema: Type[BaseModel]):
        class MockStructuredLLM:
            async def ainvoke(self, messages):
                return schema(
                    agent_id="mock_id",
                    ticker="AAPL",
                    score=0.8,
                    confidence=0.9,
                    rationale="Tool data looked good."
                )
        return MockStructuredLLM()

async def test_agent():
    llm = MockLLM()
    agent = FundamentalAnalystAgent(llm=llm)
    
    print("\nExecuting analysis on AAPL (Mocked)...")
    result = await agent.analyze("AAPL", data={"source": "test"})
    
    print("\n=== FINAL RESULT ===")
    print(result)

if __name__ == "__main__":
    asyncio.run(test_agent())

