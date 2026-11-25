import asyncio
from nemoguardrails import LLMRails, RailsConfig
from nat.runtime.loader import load_workflow


class NvidiaFintechOrchestrator:
    def __init__(self, nat_config: str, rails_dir: str):
        self.nat_config = nat_config
        self.rails = LLMRails(RailsConfig.from_path(rails_dir))

    async def process_request(self, query: str) -> str:
        # 1. Screen input via NeMo Guardrails
        guard = await self.rails.generate_async(messages=[{"role": "user", "content": query}])
        if "I cannot" in guard.get("content", ""):
            return guard["content"]

        # 2. Run Supervisor -> Specialist Multi-Agent Workflow
        async with load_workflow(self.nat_config) as workflow:
            async with workflow.run(query) as runner:
                result = await runner.result(to_type=str)

        return result


if __name__ == "__main__":
    orchestrator = NvidiaFintechOrchestrator(
        nat_config="configs/multi_agent.yml",
        rails_dir="configs/guardrails",
    )
    prompt = (
        "Evaluate a portfolio worth 5,000,000 with 14% expected return and 18% volatility, "
        "and audit an incoming wire transfer of 1,500,000 from a KYC-verified account."
    )
    print(asyncio.run(orchestrator.process_request(prompt)))
