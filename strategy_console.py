import json
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from clickup_taskrev import fetch_list_source, fetch_doc_source, SOURCES

load_dotenv()

SYSTEM_PROMPT = """당신은 사용자의 ClickUp 태스크와 개인 행동 원칙을 바탕으로 가장 전략적인 실행 순서를 계산하는 엔진입니다.
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트, 설명, 마크다운 코드블록 없이 순수 JSON만 반환합니다.

{
  "actions": [
    {
      "task_name": "태스크 이름",
      "action_type": "priority_up | priority_down | do_now | hold | escalate | create_subtask",
      "rationale": "왜 이 액션이 전략적인지 1-2문장, 원칙과 연결지어 설명",
      "clickup_update": "ClickUp 앱에서 그대로 적용할 수 있는 구체적 지시 (예: 우선순위를 '긴급'으로 변경, 마감일을 07/08로 이동)"
    }
  ]
}

우선순위가 높은 액션부터 순서대로 배열하세요. 감정적 서두나 동기부여 문구는 절대 넣지 마세요."""


def get_strategy(api_key: str, tasks_text: str, principles_text: str) -> list[dict]:
    client = Anthropic(api_key=api_key)
    user_content = (
        f"[태스크 목록]\n{tasks_text}\n\n"
        f"[행동 원칙]\n{principles_text or '(제공된 원칙 없음 — 일반적인 마감/중요도 기준으로 판단)'}"
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    text = next(b.text for b in response.content if b.type == "text")
    cleaned = text.replace("```json", "").replace("```", "").strip()
    parsed = json.loads(cleaned)  # let this raise — a silent bad-parse is worse than a crash
    return parsed["actions"]


def print_actions(actions: list[dict]) -> None:
    for i, a in enumerate(actions, 1):
        print(f"{i}. [{a.get('action_type', 'review')}] {a.get('task_name', '(제목 없음)')}")
        print(f"   → {a.get('rationale', '')}")
        if a.get("clickup_update"):
            print(f"   ClickUp: {a['clickup_update']}")
        print()


def main() -> None:
    clickup_key = os.getenv("CLICKUP_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if not clickup_key:
        raise SystemExit("CLICKUP_API_KEY is not set")
    if not anthropic_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set")

    tasks_source = next(s for s in SOURCES if s["type"] == "list")
    principles_source = next(s for s in SOURCES if s["type"] == "doc")

    tasks_text = fetch_list_source(clickup_key, tasks_source)
    principles_text = fetch_doc_source(clickup_key, principles_source)

    actions = get_strategy(anthropic_key, tasks_text, principles_text)
    print_actions(actions)


if __name__ == "__main__":
    main()