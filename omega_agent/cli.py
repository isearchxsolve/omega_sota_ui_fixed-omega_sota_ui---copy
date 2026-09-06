"""OMEGA CLI — run goals from the command line."""

import argparse
import asyncio
import json
import sys

from omega_agent import OmegaAgent, Config


def main():
    parser = argparse.ArgumentParser(
        description="OMEGA Agent — True Master of All Trades, True Action Taker",
    )
    parser.add_argument("goal", nargs="?", help="Goal to execute")
    parser.add_argument("--domain", "-d", help="Domain hint (crypto_trading, research, coding, planning)")
    parser.add_argument("--max-time", "-t", type=int, default=300, help="Max execution time (seconds)")
    parser.add_argument("--mock", action="store_true", help="Force mock LLM mode (ignore GROQ_API_KEY)")
    parser.add_argument("--json", action="store_true", help="Output JSON result")
    parser.add_argument("--serve", action="store_true", help="Start FastAPI server")
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Launch OMEGA Web UI (FastAPI + live SSE progress — recommended)",
    )
    parser.add_argument(
        "--ui-gradio",
        action="store_true",
        help="Launch legacy Gradio UI (optional; progress may not stream reliably)",
    )
    parser.add_argument("--share", action="store_true", help="Create public Gradio link (with --ui-gradio)")
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port: API (8000), Web UI (7860 with --ui), Gradio (7860 with --ui-gradio)",
    )
    parser.add_argument("--benchmark", action="store_true", help="Run SOTA benchmark suite")

    args = parser.parse_args()

    if args.serve:
        import uvicorn
        uvicorn.run("omega_agent.api:app", host="0.0.0.0", port=args.port, reload=False)
        return

    if args.ui_gradio:
        from omega_agent.ui.gradio_app import launch_ui

        config = Config(use_mock_llm=args.mock)
        launch_ui(
            config=config,
            share=args.share,
            server_port=args.port if args.port != 8000 else 7860,
        )
        return

    if args.ui:
        from omega_agent.ui.web_app import launch_web_ui

        config = Config(use_mock_llm=args.mock)
        ui_port = 7860 if args.port == 8000 else args.port
        launch_web_ui(config=config, port=ui_port)
        return

    if args.benchmark:
        from test_omega_sota import run_full_benchmark
        report = asyncio.run(run_full_benchmark())
        print(json.dumps({
            "winner": report.winner,
            "test_cases": report.test_cases_count,
            "baselines": report.baselines,
        }, indent=2))
        return

    if not args.goal:
        parser.print_help()
        sys.exit(1)

    config = Config(use_mock_llm=args.mock)
    agent = OmegaAgent(config=config)
    result = asyncio.run(agent.run(goal=args.goal, domain=args.domain, max_time=args.max_time))

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"\n{'='*60}")
        print("OMEGA RESULT")
        print(f"{'='*60}")
        print(f"Success:  {result.success}")
        print(f"Domain:   {result.domain}")
        print(f"Action:   {result.decision.action if result.decision else 'N/A'}")
        print(f"Confidence: {result.decision.confidence:.0%}" if result.decision else "")
        print(f"Latency:  {result.latency:.2f}s")
        print(f"Cost:     ${result.cost:.4f}")
        print(f"\n{result.output}")
        print(f"{'='*60}\n")

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
