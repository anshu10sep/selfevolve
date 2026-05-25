import asyncio
import logging
from langchain_core.messages import AIMessage
from agents.analyst_agents import FundamentalAnalystAgent, TechnicalAnalystAgent
from agents.skills.jarvis.agent_messaging import register_agent_instance

logging.basicConfig(level=logging.INFO)

class MockLLM:
    def __init__(self, name):
        self.name = name

    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, messages):
        # Fake a tool call if we're Fundamental
        if self.name == "fundamental" and not getattr(self, "called", False):
            self.called = True
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "delegate_task_to_agent",
                    "args": {"agent_name": "Technical Analyst", "task": "What is the RSI for AAPL?"},
                    "id": "call_delegate"
                }]
            )
        # Final response
        if self.name == "technical":
            return AIMessage(content="AAPL RSI is 65.2 (Mocked Technical Response)")
        return AIMessage(content="Final fundamental analysis combining technicals.")

    def with_structured_output(self, schema):
        class MockStructuredLLM:
            async def ainvoke(self, messages):
                return schema(
                    agent_id="mock_id",
                    ticker="AAPL",
                    score=0.8,
                    confidence=0.9,
                    rationale="Technical data confirmed fundamental thesis."
                )
        return MockStructuredLLM()

async def test_peer_messaging():
    # Setup agents
    tech_llm = MockLLM("technical")
    tech_agent = TechnicalAnalystAgent(llm=tech_llm)
    
    fund_llm = MockLLM("fundamental")
    fund_agent = FundamentalAnalystAgent(llm=fund_llm)
    
    # Register them so they can message each other
    register_agent_instance(tech_agent.name, tech_agent)
    register_agent_instance(fund_agent.name, fund_agent)
    
    print(f"Fundamental Agent tools: {fund_agent.get_available_tools()}")
    
    print("\nExecuting Fundamental Analysis. It should invoke delegate_task_to_agent...")
    result = await fund_agent.analyze("AAPL", data={"source": "test"})
    
    print("\n=== FINAL RESULT ===")
    print(result)

if __name__ == "__main__":
    asyncio.run(test_peer_messaging())
